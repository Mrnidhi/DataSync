"""Tests for datasight.analyzer.code_analyzer"""

import os
import tempfile

import pytest

from datasight.analyzer.code_analyzer import CodeAnalyzer


class TestCodeAnalyzer:
    """Test DAG source code analysis."""

    SAMPLE_DAG = '''
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime

def my_extract():
    """Extract data from source."""
    print("Extracting...")
    return {"rows": 100}

def my_transform():
    """Transform the data."""
    result = 1 / 0  # Bug!
    return result

with DAG(
    dag_id="test_dag",
    start_date=datetime(2024, 1, 1),
    schedule_interval="@daily",
) as dag:
    t1 = PythonOperator(
        task_id="extract_task",
        python_callable=my_extract,
    )
    t2 = PythonOperator(
        task_id="transform_task",
        python_callable=my_transform,
    )
    t1 >> t2
'''

    def setup_method(self):
        """Create a temp DAGs directory with sample files."""
        from datasight.config.settings import get_settings
        get_settings.cache_clear()

        self.temp_dir = tempfile.mkdtemp()
        self.dag_file = os.path.join(self.temp_dir, "test_dag.py")
        with open(self.dag_file, "w") as f:
            f.write(self.SAMPLE_DAG)

        # Create a referenced SQL file
        self.sql_file = os.path.join(self.temp_dir, "query.sql")
        with open(self.sql_file, "w") as f:
            f.write("SELECT * FROM users WHERE active = true;")

    def teardown_method(self):
        """Clean up temp files."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_dag_file(self):
        """Should locate a DAG file by its dag_id."""
        analyzer = CodeAnalyzer()
        analyzer.dags_folder = self.temp_dir

        result = analyzer.find_dag_file("test_dag")
        assert result is not None
        assert result.endswith("test_dag.py")

    def test_find_dag_file_not_found(self):
        """Should return None for non-existent dag_id."""
        analyzer = CodeAnalyzer()
        analyzer.dags_folder = self.temp_dir

        result = analyzer.find_dag_file("nonexistent_dag")
        assert result is None

    def test_find_dag_file_missing_folder(self):
        """Should return None if DAGs folder doesn't exist."""
        analyzer = CodeAnalyzer()
        analyzer.dags_folder = "/nonexistent/path"

        result = analyzer.find_dag_file("test_dag")
        assert result is None

    def test_read_file(self):
        """Should read file contents."""
        analyzer = CodeAnalyzer()
        content = analyzer.read_file(self.dag_file)
        assert "my_extract" in content
        assert "my_transform" in content

    def test_read_file_not_found(self):
        """Should return empty string for missing files."""
        analyzer = CodeAnalyzer()
        content = analyzer.read_file("/nonexistent/file.py")
        assert content == ""

    def test_get_context(self):
        """get_context should return full DAG context."""
        analyzer = CodeAnalyzer()
        analyzer.dags_folder = self.temp_dir

        result = analyzer.get_context("test_dag", "transform_task")
        assert result["source"] != ""
        assert result["filepath"] is not None
        assert "my_transform" in result["source"]

    def test_get_context_not_found(self):
        """get_context should return empty dict for missing DAGs."""
        analyzer = CodeAnalyzer()
        analyzer.dags_folder = self.temp_dir

        result = analyzer.get_context("nonexistent")
        assert result["source"] == ""
        assert result["filepath"] is None

    def test_extract_function(self):
        """Should extract a function definition from source code."""
        func = CodeAnalyzer._extract_function(self.SAMPLE_DAG, "my_transform")
        assert "def my_transform" in func
        assert "1 / 0" in func

    def test_extract_function_not_found(self):
        """Should return empty string for non-existent function."""
        func = CodeAnalyzer._extract_function(self.SAMPLE_DAG, "nonexistent_func")
        assert func == ""

    def test_find_referenced_files(self):
        """Should discover referenced SQL files from DAG source."""
        # Add a reference to the SQL file in the DAG
        dag_with_ref = self.SAMPLE_DAG + '\nsql_path = "query.sql"\n'
        analyzer = CodeAnalyzer()
        refs = analyzer.find_referenced_files(dag_with_ref, self.temp_dir)
        sql_refs = [r for r in refs if r["type"] == "sql"]
        assert len(sql_refs) >= 1
        assert "SELECT * FROM users" in sql_refs[0]["content"]

    def test_extract_task_callable(self):
        """Should extract the callable for a specific task_id."""
        analyzer = CodeAnalyzer()
        result = analyzer._extract_task_callable(self.SAMPLE_DAG, "transform_task")
        assert "my_transform" in result or result == ""
