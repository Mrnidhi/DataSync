"""Tests for datasight.llm.engine"""

import pytest

from datasight.llm.engine import Diagnosis, IncidentAnalysis, LLMEngine, Patch


class TestDiagnosisParsing:
    """Test the LLM response parser."""

    def test_parse_structured_response(self):
        """Should parse well-formatted LLM responses."""
        response = """ROOT_CAUSE: Column 'user_email' does not exist in the raw_users table
EXPLANATION: The dbt model references column user_email but the actual column name is email_address. This causes a compilation failure.
SEVERITY: medium
CONFIDENCE: 0.92"""

        diag = LLMEngine._parse_diagnosis(response, "sql")
        assert "user_email" in diag.root_cause
        assert "email_address" in diag.explanation
        assert diag.severity == "medium"
        assert diag.confidence == pytest.approx(0.92, abs=0.01)
        assert diag.error_type == "sql"

    def test_parse_partial_response(self):
        """Should handle responses missing some fields."""
        response = """ROOT_CAUSE: Missing import statement
EXPLANATION: The pandas library is not installed."""

        diag = LLMEngine._parse_diagnosis(response, "import")
        assert "import" in diag.root_cause.lower()
        assert diag.severity == "medium"  # default
        assert diag.confidence == 0.5  # default

    def test_parse_unstructured_response(self):
        """Should fallback gracefully for unstructured responses."""
        response = "The error appears to be a missing column in the database."

        diag = LLMEngine._parse_diagnosis(response, "unknown")
        assert diag.root_cause != ""
        assert diag.error_type == "unknown"

    def test_parse_confidence_bounds(self):
        """Confidence should be clamped between 0.0 and 1.0."""
        response = "ROOT_CAUSE: Test\nCONFIDENCE: 2.5"
        diag = LLMEngine._parse_diagnosis(response, "unknown")
        assert diag.confidence == 1.0

        response2 = "ROOT_CAUSE: Test\nCONFIDENCE: -0.5"
        diag2 = LLMEngine._parse_diagnosis(response2, "unknown")
        assert diag2.confidence == 0.0

        response3 = "ROOT_CAUSE: Test\nCONFIDENCE: 0.75"
        diag3 = LLMEngine._parse_diagnosis(response3, "unknown")
        assert diag3.confidence == pytest.approx(0.75, abs=0.01)


class TestPatchParsing:
    """Test code patch parsing from LLM responses."""

    ORIGINAL_CODE = """def my_task():
    result = df.select("user_email")
    return result"""

    def test_parse_valid_patch(self):
        """Should parse a valid patch response."""
        response = """DESCRIPTION: Fixed column name from user_email to email_address
RISK_LEVEL: low
PATCHED_CODE:
```python
def my_task():
    result = df.select("email_address")
    return result
```"""

        patch = LLMEngine._parse_patch(response, self.ORIGINAL_CODE, "dags/my_dag.py")
        assert patch is not None
        assert patch.filepath == "dags/my_dag.py"
        assert "email_address" in patch.patched_code
        assert patch.risk_level == "low"
        assert patch.diff != ""

    def test_parse_no_code_block(self):
        """Should return None if no code block found."""
        response = "DESCRIPTION: Some fix\nRISK_LEVEL: low\nNo code provided."
        patch = LLMEngine._parse_patch(response, self.ORIGINAL_CODE, "dag.py")
        assert patch is None

    def test_parse_identical_code(self):
        """Should return None if patched code is identical to original."""
        response = f"""DESCRIPTION: No change
RISK_LEVEL: low
PATCHED_CODE:
```python
{self.ORIGINAL_CODE}
```"""
        patch = LLMEngine._parse_patch(response, self.ORIGINAL_CODE, "dag.py")
        assert patch is None


class TestPromptBuilding:
    """Test prompt construction for the LLM."""

    def test_diagnosis_prompt_includes_context(self):
        """User prompt should include all available incident data."""
        incident = {
            "dag_id": "test_dag",
            "task_id": "broken_task",
            "traceback": "Traceback: SomeError",
            "sql_error": "column not found",
            "dag_source": "def my_func(): pass",
            "task_source": "def broken(): raise Error",
        }
        prompt = LLMEngine._build_diagnosis_user_prompt(incident)
        assert "test_dag" in prompt
        assert "broken_task" in prompt
        assert "Traceback: SomeError" in prompt
        assert "column not found" in prompt
        assert "my_func" in prompt

    def test_diagnosis_system_prompt_structure(self):
        """System prompt should contain response format instructions."""
        prompt = LLMEngine._build_diagnosis_system_prompt()
        assert "ROOT_CAUSE" in prompt
        assert "SEVERITY" in prompt
        assert "CONFIDENCE" in prompt

    def test_patch_system_prompt_structure(self):
        """Patch system prompt should contain format instructions."""
        prompt = LLMEngine._build_patch_system_prompt()
        assert "PATCHED_CODE" in prompt
        assert "RISK_LEVEL" in prompt


class TestDiagnosisDataclass:
    """Test the Diagnosis and Patch dataclasses."""

    def test_diagnosis_defaults(self):
        """Diagnosis should have sensible defaults."""
        d = Diagnosis(root_cause="test", explanation="test explanation")
        assert d.severity == "medium"
        assert d.confidence == 0.0
        assert d.error_type == "unknown"

    def test_patch_defaults(self):
        """Patch should have sensible defaults."""
        p = Patch(
            filepath="dag.py",
            original_code="old",
            patched_code="new",
            diff="- old\n+ new",
            description="fix",
        )
        assert p.risk_level == "low"

    def test_incident_analysis_defaults(self):
        """IncidentAnalysis should default to empty patches."""
        analysis = IncidentAnalysis(
            diagnosis=Diagnosis(root_cause="test", explanation="test"),
        )
        assert analysis.patches == []
        assert analysis.raw_llm_response == ""
