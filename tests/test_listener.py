"""Tests for datasight.listener.listener"""

from unittest.mock import MagicMock, patch

import pytest

from datasight.listener.listener import DataSightListener


class TestDataSightListener:
    """Test the Airflow Listener hooks."""

    def setup_method(self):
        from datasight.config.settings import get_settings
        get_settings.cache_clear()

    def _mock_task_instance(
        self, dag_id="test_dag", task_id="test_task",
        run_id="manual__2024-01-01", try_number=1,
    ):
        ti = MagicMock()
        ti.dag_id = dag_id
        ti.task_id = task_id
        ti.run_id = run_id
        ti.try_number = try_number
        ti.execution_date = "2024-01-01T00:00:00"
        return ti

    @patch("datasight.listener.listener.get_settings")
    def test_disabled_listener_does_nothing(self, mock_settings):
        """When disabled, the listener should exit immediately."""
        settings = MagicMock()
        settings.enabled = False
        mock_settings.return_value = settings

        listener = DataSightListener()
        ti = self._mock_task_instance()

        # Should not raise or do anything
        listener.on_task_instance_failed(None, ti, None)

    @patch("datasight.listener.listener.get_settings")
    def test_on_task_instance_failed_catches_errors(self, mock_settings):
        """Listener should not crash even if internal processing fails."""
        settings = MagicMock()
        settings.enabled = True
        mock_settings.return_value = settings

        listener = DataSightListener()
        ti = self._mock_task_instance()

        # This will fail internally (no real Airflow API), but should not raise
        listener.on_task_instance_failed(None, ti, Exception("test error"))

    def test_on_task_instance_success_noop(self):
        """Success handler should not raise."""
        listener = DataSightListener()
        ti = self._mock_task_instance()
        listener.on_task_instance_success(None, ti)

    def test_on_task_instance_running_noop(self):
        """Running handler should not raise."""
        listener = DataSightListener()
        ti = self._mock_task_instance()
        listener.on_task_instance_running(None, ti)
