"""
DataSight Code Analyzer — reads DAG source code and referenced files.

When a task fails, this module locates the DAG's Python source file,
reads it, and also discovers any referenced SQL files, dbt models,
or configuration files to provide full context to the LLM.
"""

from __future__ import annotations

import ast
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from datasight.config.settings import get_settings

logger = logging.getLogger("datasight.analyzer.code")


class CodeAnalyzer:
    """Reads and analyzes DAG source code and referenced files."""

    def __init__(self) -> None:
        settings = get_settings()
        self.dags_folder = settings.dags_folder

    def find_dag_file(self, dag_id: str) -> Optional[str]:
        """
        Locate the Python file that defines the given DAG.

        Strategy:
        1. Search all .py files in the DAGs folder
        2. Look for `dag_id="{dag_id}"` or `DAG("{dag_id}"` patterns
        """
        dags_path = Path(self.dags_folder)
        if not dags_path.exists():
            logger.warning("DAGs folder not found: %s", self.dags_folder)
            return None

        for py_file in dags_path.rglob("*.py"):
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                # Check for DAG ID in common patterns
                patterns = [
                    f'dag_id="{dag_id}"',
                    f"dag_id='{dag_id}'",
                    f'DAG("{dag_id}"',
                    f"DAG('{dag_id}'",
                    f'"{dag_id}"',
                ]
                if any(p in content for p in patterns):
                    logger.info("Found DAG file for %s: %s", dag_id, py_file)
                    return str(py_file)
            except Exception as e:
                logger.debug("Could not read %s: %s", py_file, e)

        logger.warning("Could not find DAG file for dag_id=%s", dag_id)
        return None

    def read_file(self, filepath: str) -> str:
        """Read a file's contents safely."""
        try:
            return Path(filepath).read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            logger.error("Cannot read file %s: %s", filepath, e)
            return ""

    def find_referenced_files(self, source_code: str, base_dir: str) -> List[Dict[str, str]]:
        """
        Discover files referenced by the DAG source code.

        Looks for:
        - SQL file paths (*.sql)
        - dbt model references
        - Config file paths (*.yaml, *.yml, *.json, *.cfg)
        - Python module imports within the DAGs folder
        """
        referenced = []
        base_path = Path(base_dir)

        # Pattern 1: String literals that look like file paths
        file_path_pattern = re.compile(
            r"""['"]([\w./\-]+\.(?:sql|yaml|yml|json|cfg|py|csv|conf))['""]""",
        )
        for match in file_path_pattern.finditer(source_code):
            rel_path = match.group(1)
            abs_path = base_path / rel_path
            if abs_path.exists():
                referenced.append({
                    "path": str(abs_path),
                    "type": abs_path.suffix.lstrip("."),
                    "content": self.read_file(str(abs_path)),
                })

        # Pattern 2: dbt model references like ref('model_name')
        dbt_ref_pattern = re.compile(r"""ref\(['"]([\w]+)['"]\)""")
        for match in dbt_ref_pattern.finditer(source_code):
            model_name = match.group(1)
            # Search for the model file in common dbt paths
            for dbt_dir in ["models", "dbt/models", "../dbt/models"]:
                model_path = base_path / dbt_dir / f"{model_name}.sql"
                if model_path.exists():
                    referenced.append({
                        "path": str(model_path),
                        "type": "dbt_model",
                        "content": self.read_file(str(model_path)),
                    })

        # Pattern 3: Python imports from the same DAGs directory
        import_pattern = re.compile(r"from\s+([\w.]+)\s+import|import\s+([\w.]+)")
        for match in import_pattern.finditer(source_code):
            module_name = match.group(1) or match.group(2)
            # Convert module path to file path
            module_file = base_path / (module_name.replace(".", "/") + ".py")
            if module_file.exists() and str(module_file) not in [r["path"] for r in referenced]:
                referenced.append({
                    "path": str(module_file),
                    "type": "python",
                    "content": self.read_file(str(module_file)),
                })

        logger.info("Found %d referenced files in DAG source", len(referenced))
        return referenced

    def get_context(self, dag_id: str, task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Build the full code context for a DAG failure.

        Returns:
            Dict with: source (DAG code), filepath, referenced_files, task_source
        """
        dag_file = self.find_dag_file(dag_id)

        if not dag_file:
            return {
                "source": "",
                "filepath": None,
                "referenced_files": [],
                "task_source": "",
            }

        source = self.read_file(dag_file)
        base_dir = os.path.dirname(dag_file)

        # Find referenced files
        referenced_files = self.find_referenced_files(source, base_dir)

        # Try to extract the specific task's callable source
        task_source = ""
        if task_id:
            task_source = self._extract_task_callable(source, task_id)

        result = {
            "source": source,
            "filepath": dag_file,
            "referenced_files": referenced_files,
            "task_source": task_source,
        }

        logger.info(
            "Code context built for %s — source_len=%d, refs=%d",
            dag_id, len(source), len(referenced_files),
        )

        return result

    def _extract_task_callable(self, source: str, task_id: str) -> str:
        """
        Try to extract the Python function used by a specific task.

        Looks for patterns like:
          task_id="my_task" ... python_callable=my_function
          @task(task_id="my_task")
        Then finds the function definition.
        """
        # Pattern: python_callable associated with this task_id
        callable_pattern = re.compile(
            rf"""task_id\s*=\s*['"]{task_id}['"].*?python_callable\s*=\s*(\w+)""",
            re.DOTALL,
        )
        match = callable_pattern.search(source)

        if match:
            func_name = match.group(1)
            return self._extract_function(source, func_name)

        # Pattern: @task decorator with task_id
        decorator_pattern = re.compile(
            rf"""@task.*?task_id\s*=\s*['"]{task_id}['"]""",
            re.DOTALL,
        )
        dec_match = decorator_pattern.search(source)
        if dec_match:
            # Find the def immediately following the decorator
            remaining = source[dec_match.end():]
            func_match = re.search(r"def\s+(\w+)", remaining)
            if func_match:
                return self._extract_function(source, func_match.group(1))

        return ""

    @staticmethod
    def _extract_function(source: str, func_name: str) -> str:
        """Extract a full function definition from source code using AST."""
        try:
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == func_name:
                        lines = source.split("\n")
                        start = node.lineno - 1
                        end = node.end_lineno if hasattr(node, "end_lineno") else start + 20
                        return "\n".join(lines[start:end])
        except SyntaxError:
            # Fallback: regex extraction
            pattern = re.compile(
                rf"(def\s+{func_name}\s*\(.*?\n(?:(?:    |\t).*\n)*)",
                re.MULTILINE,
            )
            match = pattern.search(source)
            if match:
                return match.group(1)

        return ""
