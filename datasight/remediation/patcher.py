"""
DataSight Patcher — applies code patches to DAG files.

Supports two modes:
  - DIRECT_WRITE: Write directly to the DAGs folder (dev/local)
  - GIT_PR: Commit to a branch and create a PR (production)
"""

from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.remediation.patcher")


class Patcher:
    """Applies code patches to filesystem or via Git."""

    def apply(self, filepath: str, patched_code: str) -> None:
        """
        Apply a patch by writing the fixed code to the target file.

        Creates a backup of the original file before overwriting.
        """
        target = Path(filepath)

        if not target.exists():
            logger.error("Target file does not exist: %s", filepath)
            raise FileNotFoundError(f"Cannot patch non-existent file: {filepath}")

        # Create backup
        backup_path = f"{filepath}.datasight.bak"
        shutil.copy2(filepath, backup_path)
        logger.info("Backup created: %s", backup_path)

        # Write patched code
        try:
            target.write_text(patched_code, encoding="utf-8")
            logger.info("Patch applied to %s", filepath)
        except Exception as e:
            # Restore backup on failure
            logger.error("Patch failed, restoring backup: %s", e)
            shutil.copy2(backup_path, filepath)
            raise

    def rollback(self, filepath: str) -> bool:
        """Rollback a patched file to its backup."""
        backup_path = f"{filepath}.datasight.bak"
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, filepath)
            os.remove(backup_path)
            logger.info("Rolled back %s", filepath)
            return True
        logger.warning("No backup found for %s", filepath)
        return False

    def trigger_dag_rerun(self, dag_id: str) -> bool:
        """Trigger a DAG rerun via the Airflow REST API after a successful patch."""
        settings = get_settings()
        try:
            import requests
            from requests.auth import HTTPBasicAuth

            response = requests.post(
                f"{settings.airflow_api_url}/dags/{dag_id}/dagRuns",
                json={"conf": {"triggered_by": "datasight_auto_fix"}},
                auth=HTTPBasicAuth(settings.airflow_username, settings.airflow_password),
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if response.ok:
                logger.info("DAG rerun triggered for %s", dag_id)
                return True
            else:
                logger.error("Failed to trigger rerun: %s", response.text)
                return False

        except Exception as e:
            logger.error("Error triggering DAG rerun: %s", e)
            return False
