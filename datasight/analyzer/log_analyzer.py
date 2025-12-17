"""
DataSight Log Analyzer — fetches and parses Airflow task logs.

Extracts structured information from raw task logs:
- Python tracebacks
- Error messages and exception types
- SQL errors (for dbt/Spark tasks)
- Key timestamps
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Optional

import requests
from requests.auth import HTTPBasicAuth

from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.analyzer.logs")


class LogAnalyzer:
    """Fetches Airflow task logs and extracts diagnostic information."""

    def __init__(self) -> None:
        settings = get_settings()
        self.base_url = settings.airflow_api_url
        self.auth = HTTPBasicAuth(settings.airflow_username, settings.airflow_password)

    def fetch_logs(
        self,
        dag_id: str,
        task_id: str,
        run_id: str,
        try_number: int = 1,
    ) -> str:
        """Fetch raw task logs from the Airflow REST API."""
        import urllib.parse

        encoded_run_id = urllib.parse.quote(run_id)
        url = (
            f"{self.base_url}/dags/{dag_id}/dagRuns/{encoded_run_id}"
            f"/taskInstances/{task_id}/logs/{try_number}"
        )

        try:
            response = requests.get(
                url,
                auth=self.auth,
                headers={"Accept": "text/plain"},
                timeout=10,
            )
            response.raise_for_status()
            return response.text
        except requests.exceptions.ConnectionError:
            logger.error("Cannot connect to Airflow API at %s", self.base_url)
            return ""
        except requests.exceptions.Timeout:
            logger.error("Airflow API request timed out")
            return ""
        except requests.exceptions.RequestException as e:
            logger.error("Error fetching logs: %s", e)
            return ""

    def extract_traceback(self, raw_logs: str) -> str:
        """Extract the Python traceback from raw Airflow task logs."""
        # Look for standard Python traceback pattern
        tb_pattern = re.compile(
            r"(Traceback \(most recent call last\):.*?)(?=\[\d{4}-|\Z)",
            re.DOTALL,
        )
        match = tb_pattern.search(raw_logs)
        if match:
            return match.group(1).strip()

        # Fallback: look for ERROR lines
        error_lines = [
            line for line in raw_logs.split("\n")
            if "ERROR" in line or "Exception" in line or "Error" in line
        ]
        return "\n".join(error_lines[-20:]) if error_lines else ""

    def extract_sql_errors(self, raw_logs: str) -> Optional[str]:
        """Extract SQL-specific errors (dbt, Spark SQL)."""
        sql_patterns = [
            r"((?:ERROR|HINT|LINE \d+).*?)(?=\[\d{4}-|\Z)",
            r"(AnalysisException:.*?)(?=\n\n|\Z)",
            r"(Compilation Error.*?)(?=\n\n|\Z)",
        ]
        for pattern in sql_patterns:
            match = re.search(pattern, raw_logs, re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    def analyze(
        self,
        dag_id: str,
        task_id: str,
        run_id: str,
        try_number: int = 1,
    ) -> Dict[str, Any]:
        """
        Full analysis pipeline: fetch logs → extract traceback → extract SQL errors.

        Returns:
            Dict with keys: raw_logs, traceback, sql_error, log_snippet, error_type
        """
        raw_logs = self.fetch_logs(dag_id, task_id, run_id, try_number)

        if not raw_logs:
            return {
                "raw_logs": "",
                "traceback": "",
                "sql_error": None,
                "log_snippet": "",
                "error_type": "unknown",
            }

        traceback = self.extract_traceback(raw_logs)
        sql_error = self.extract_sql_errors(raw_logs)

        # Determine error type
        error_type = "unknown"
        if sql_error:
            error_type = "sql"
        elif "ModuleNotFoundError" in traceback:
            error_type = "import"
        elif "ConnectionError" in traceback or "timeout" in traceback.lower():
            error_type = "connection"
        elif "KeyError" in traceback or "TypeError" in traceback:
            error_type = "runtime"
        elif traceback:
            error_type = "exception"

        # Create a concise snippet (last 2000 chars) for LLM context
        log_snippet = raw_logs[-2000:] if len(raw_logs) > 2000 else raw_logs

        result = {
            "raw_logs": raw_logs,
            "traceback": traceback,
            "sql_error": sql_error,
            "log_snippet": log_snippet,
            "error_type": error_type,
        }

        logger.info(
            "Log analysis complete for %s.%s — error_type=%s, traceback_len=%d",
            dag_id, task_id, error_type, len(traceback),
        )

        return result
