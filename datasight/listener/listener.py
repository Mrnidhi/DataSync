"""
DataSight Airflow Listener — hooks into task lifecycle events in real-time.

Uses the Airflow Listener API (2.7+) to intercept task failures the instant
they happen, without polling. This is the entry point for the entire
DataSight diagnostic pipeline.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from datasight.config.settings import get_settings
from datasight.observability.metrics import record_failure_detected

if TYPE_CHECKING:
    from airflow.models.taskinstance import TaskInstance
    from airflow.utils.state import TaskInstanceState

logger = logging.getLogger("datasight.listener")


class DataSightListener:
    """
    Airflow Listener that triggers DataSight diagnostics on task failure.

    Registered via:
      [listeners]
      listener_class = datasight.listener.listener.DataSightListener

    Or via env var:
      AIRFLOW__LISTENERS__LISTENER_CLASS=datasight.listener.listener.DataSightListener
    """

    def on_task_instance_failed(
        self,
        previous_state: TaskInstanceState | None,
        task_instance: TaskInstance,
        error: BaseException | None,
    ) -> None:
        """Called by Airflow the instant a task instance transitions to FAILED."""
        settings = get_settings()
        if not settings.enabled:
            return

        dag_id = task_instance.dag_id
        task_id = task_instance.task_id
        run_id = task_instance.run_id
        try_number = task_instance.try_number
        execution_date = str(task_instance.execution_date)

        logger.warning(
            "DataSight detected failure: dag_id=%s task_id=%s run_id=%s try=%d",
            dag_id, task_id, run_id, try_number,
        )
        record_failure_detected(dag_id)

        # Dispatch to the diagnostic pipeline asynchronously
        # We import here to avoid circular imports and heavy loading at plugin init
        try:
            from datasight.analyzer.log_analyzer import LogAnalyzer
            from datasight.analyzer.code_analyzer import CodeAnalyzer

            # Step 1: Fetch and parse the task logs
            log_analyzer = LogAnalyzer()
            log_result = log_analyzer.analyze(
                dag_id=dag_id,
                task_id=task_id,
                run_id=run_id,
                try_number=try_number,
            )

            # Step 2: Read the DAG source code for context
            code_analyzer = CodeAnalyzer()
            code_context = code_analyzer.get_context(dag_id=dag_id, task_id=task_id)

            # Step 3: Build the incident payload
            incident_data = {
                "dag_id": dag_id,
                "task_id": task_id,
                "run_id": run_id,
                "try_number": try_number,
                "execution_date": execution_date,
                "error_message": str(error) if error else None,
                "traceback": log_result.get("traceback", ""),
                "log_snippet": log_result.get("log_snippet", ""),
                "dag_source": code_context.get("source", ""),
                "referenced_files": code_context.get("referenced_files", []),
            }

            logger.info(
                "DataSight incident created for %s.%s — dispatching to LLM engine",
                dag_id, task_id,
            )

            # Route through the Approval Gateway for full diagnostic pipeline
            from datasight.approval.gateway import ApprovalGateway

            gateway = ApprovalGateway()
            incident = gateway.create_incident(incident_data)
            gateway.process_incident(incident)

        except Exception as exc:
            logger.error("DataSight listener error: %s", exc, exc_info=True)

    def on_task_instance_success(
        self,
        previous_state: TaskInstanceState | None,
        task_instance: TaskInstance,
    ) -> None:
        """Optional: track recoveries after a previous failure."""
        pass

    def on_task_instance_running(
        self,
        previous_state: TaskInstanceState | None,
        task_instance: TaskInstance,
    ) -> None:
        """Optional: track task starts for latency monitoring."""
        pass
