"""Tests for datasight.analyzer.log_analyzer"""

import pytest
from unittest.mock import patch, MagicMock

from datasight.analyzer.log_analyzer import LogAnalyzer


class TestLogAnalyzer:
    """Test log fetching and parsing."""

    def setup_method(self):
        """Reset settings cache before each test."""
        from datasight.config.settings import get_settings
        get_settings.cache_clear()

    SAMPLE_LOG_WITH_TRACEBACK = """
[2024-03-14 10:30:15,123] {taskinstance.py:1234} INFO - Starting task
[2024-03-14 10:30:16,456] {taskinstance.py:1235} ERROR - Task failed
Traceback (most recent call last):
  File "/opt/airflow/dags/my_dag.py", line 42, in broken_transform
    result = df.select("non_existent_column")
  File "/opt/airflow/lib/spark.py", line 100, in select
    raise AnalysisException("Column not found")
AnalysisException: Column 'non_existent_column' not found
[2024-03-14 10:30:17,789] {taskinstance.py:1236} INFO - Marking task as FAILED
"""

    SAMPLE_LOG_WITH_SQL_ERROR = """
[2024-03-14 10:30:15,123] INFO - Running dbt model
ERROR: column "user_email" does not exist
HINT:  Perhaps you meant to reference the column "users.email_address".
LINE 4:     user_email as email,
"""

    SAMPLE_LOG_NO_ERROR = """
[2024-03-14 10:30:15,123] INFO - Task started
[2024-03-14 10:30:16,000] INFO - Processing 1000 records
[2024-03-14 10:30:17,000] INFO - Task completed successfully
"""

    def test_extract_traceback(self):
        """Should extract Python traceback from raw logs."""
        analyzer = LogAnalyzer()
        tb = analyzer.extract_traceback(self.SAMPLE_LOG_WITH_TRACEBACK)
        assert "Traceback (most recent call last)" in tb
        assert "AnalysisException" in tb
        assert "non_existent_column" in tb

    def test_extract_traceback_no_error(self):
        """Should return empty string when no traceback exists."""
        analyzer = LogAnalyzer()
        tb = analyzer.extract_traceback(self.SAMPLE_LOG_NO_ERROR)
        assert tb == ""

    def test_extract_sql_errors(self):
        """Should extract SQL-specific errors from dbt-style logs."""
        analyzer = LogAnalyzer()
        sql_err = analyzer.extract_sql_errors(self.SAMPLE_LOG_WITH_SQL_ERROR)
        assert sql_err is not None
        assert "user_email" in sql_err

    def test_extract_sql_errors_none(self):
        """Should return None when no SQL errors exist."""
        analyzer = LogAnalyzer()
        sql_err = analyzer.extract_sql_errors(self.SAMPLE_LOG_NO_ERROR)
        assert sql_err is None

    def test_analyze_with_empty_logs(self):
        """analyze() should handle empty logs gracefully."""
        analyzer = LogAnalyzer()
        with patch.object(analyzer, "fetch_logs", return_value=""):
            result = analyzer.analyze("dag1", "task1", "run1")
            assert result["error_type"] == "unknown"
            assert result["traceback"] == ""
            assert result["raw_logs"] == ""

    def test_analyze_classifies_import_error(self):
        """analyze() should classify ModuleNotFoundError as 'import'."""
        log = """Traceback (most recent call last):
  File "dag.py", line 1
ModuleNotFoundError: No module named 'pandas'
"""
        analyzer = LogAnalyzer()
        with patch.object(analyzer, "fetch_logs", return_value=log):
            result = analyzer.analyze("dag1", "task1", "run1")
            assert result["error_type"] == "import"

    def test_analyze_classifies_connection_error(self):
        """analyze() should classify ConnectionError as 'connection'."""
        log = """Traceback (most recent call last):
  File "dag.py", line 5
ConnectionError: Failed to connect to database
"""
        analyzer = LogAnalyzer()
        with patch.object(analyzer, "fetch_logs", return_value=log):
            result = analyzer.analyze("dag1", "task1", "run1")
            assert result["error_type"] == "connection"

    def test_analyze_classifies_sql_error(self):
        """analyze() should classify SQL errors correctly."""
        analyzer = LogAnalyzer()
        with patch.object(analyzer, "fetch_logs", return_value=self.SAMPLE_LOG_WITH_SQL_ERROR):
            result = analyzer.analyze("dag1", "task1", "run1")
            assert result["error_type"] == "sql"
            assert result["sql_error"] is not None

    def test_analyze_log_snippet_truncation(self):
        """Log snippet should be truncated to 2000 chars."""
        long_log = "x" * 5000
        analyzer = LogAnalyzer()
        with patch.object(analyzer, "fetch_logs", return_value=long_log):
            result = analyzer.analyze("dag1", "task1", "run1")
            assert len(result["log_snippet"]) == 2000

    @patch("datasight.analyzer.log_analyzer.requests.get")
    def test_fetch_logs_connection_error(self, mock_get):
        """fetch_logs should handle ConnectionError gracefully."""
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError("Connection refused")
        analyzer = LogAnalyzer()
        result = analyzer.fetch_logs("dag1", "task1", "run1")
        assert result == ""

    @patch("datasight.analyzer.log_analyzer.requests.get")
    def test_fetch_logs_timeout(self, mock_get):
        """fetch_logs should handle Timeout gracefully."""
        import requests
        mock_get.side_effect = requests.exceptions.Timeout("Timed out")
        analyzer = LogAnalyzer()
        result = analyzer.fetch_logs("dag1", "task1", "run1")
        assert result == ""
