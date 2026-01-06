"""
DataSight LLM Engine — unified interface for diagnosing failures and generating fixes.

Supports swappable backends:
  - Ollama (local, free, private)
  - OpenAI (cloud, fast, powerful)

The engine takes structured incident data and produces:
  1. A root-cause diagnosis
  2. A proposed code patch (unified diff)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from datasight.config.settings import LLMProvider, get_settings

logger = logging.getLogger("datasight.llm")


@dataclass
class Diagnosis:
    """Structured output from the LLM diagnosis step."""
    root_cause: str
    explanation: str
    severity: str = "medium"  # low, medium, high, critical
    error_type: str = "unknown"
    confidence: float = 0.0


@dataclass
class Patch:
    """A proposed code change to fix the issue."""
    filepath: str
    original_code: str
    patched_code: str
    diff: str
    description: str
    risk_level: str = "low"  # low, medium, high


@dataclass
class IncidentAnalysis:
    """Complete result from the LLM engine."""
    diagnosis: Diagnosis
    patches: List[Patch] = field(default_factory=list)
    raw_llm_response: str = ""
    model_used: str = ""


class LLMProviderInterface(Protocol):
    """Protocol that all LLM providers must implement."""

    def complete(self, prompt: str, system_prompt: str = "") -> str:
        """Send a prompt to the LLM and return the response text."""
        ...


class LLMEngine:
    """
    Unified LLM interface that dispatches to the configured provider.

    Usage:
        engine = LLMEngine()
        analysis = engine.analyze_incident(incident_data)
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.provider = self._init_provider(settings.llm_provider)
        self.model_name = settings.llm_model
        logger.info("LLM Engine initialized with provider=%s", settings.llm_provider.value)

    @staticmethod
    def _init_provider(provider_type: LLMProvider) -> LLMProviderInterface:
        """Factory method to create the appropriate LLM provider."""
        if provider_type == LLMProvider.OLLAMA:
            from datasight.llm.providers.ollama import OllamaProvider
            return OllamaProvider()
        elif provider_type == LLMProvider.OPENAI:
            from datasight.llm.providers.openai import OpenAIProvider
            return OpenAIProvider()
        else:
            raise ValueError(f"Unsupported LLM provider: {provider_type}")

    def diagnose(self, incident: Dict[str, Any]) -> Diagnosis:
        """
        Analyze a failure incident and produce a root-cause diagnosis.

        Args:
            incident: Dict with keys like traceback, log_snippet, dag_source, etc.
        """
        system_prompt = self._build_diagnosis_system_prompt()
        user_prompt = self._build_diagnosis_user_prompt(incident)

        response = self.provider.complete(user_prompt, system_prompt)

        diagnosis = self._parse_diagnosis(response, incident.get("error_type", "unknown"))
        logger.info("Diagnosis complete: %s (confidence=%.2f)", diagnosis.root_cause[:80], diagnosis.confidence)
        return diagnosis

    def generate_patch(
        self,
        diagnosis: Diagnosis,
        source_code: str,
        filepath: str,
    ) -> Optional[Patch]:
        """
        Generate a code patch to fix the diagnosed issue.

        Args:
            diagnosis: The root-cause diagnosis
            source_code: The current DAG source code
            filepath: Path to the source file
        """
        system_prompt = self._build_patch_system_prompt()
        user_prompt = self._build_patch_user_prompt(diagnosis, source_code)

        response = self.provider.complete(user_prompt, system_prompt)

        patch = self._parse_patch(response, source_code, filepath)
        if patch:
            logger.info("Patch generated for %s — risk=%s", filepath, patch.risk_level)
        return patch

    def analyze_incident(self, incident: Dict[str, Any]) -> IncidentAnalysis:
        """
        Full pipeline: diagnose the failure, then generate a fix patch.

        Args:
            incident: Structured incident data from the Listener
        """
        # Step 1: Diagnose
        diagnosis = self.diagnose(incident)

        # Step 2: Generate patch if we have source code
        patches = []
        dag_source = incident.get("dag_source", "")
        dag_filepath = incident.get("dag_filepath", "")
        if dag_source and diagnosis.confidence > 0.3:
            patch = self.generate_patch(diagnosis, dag_source, dag_filepath)
            if patch:
                patches.append(patch)

        return IncidentAnalysis(
            diagnosis=diagnosis,
            patches=patches,
            model_used=self.model_name,
        )

    # ── Prompt Construction ──────────────────────────────────────────

    @staticmethod
    def _build_diagnosis_system_prompt() -> str:
        return """You are DataSight AI, an expert Apache Airflow diagnostics engine.
Your job is to analyze task failure logs and source code to determine the EXACT root cause.

Rules:
1. Be specific — identify the exact line, variable, or config that caused the failure
2. Classify severity as: low, medium, high, or critical
3. Provide a confidence score (0.0 to 1.0) for your diagnosis
4. Focus on actionable insights, not generic advice

Respond in this exact format:
ROOT_CAUSE: [one-line summary]
EXPLANATION: [detailed explanation in 2-3 sentences]
SEVERITY: [low|medium|high|critical]
CONFIDENCE: [0.0-1.0]"""

    @staticmethod
    def _build_diagnosis_user_prompt(incident: Dict[str, Any]) -> str:
        parts = [f"# Airflow Task Failure Analysis\n"]
        parts.append(f"**DAG:** {incident.get('dag_id', 'unknown')}")
        parts.append(f"**Task:** {incident.get('task_id', 'unknown')}")

        if incident.get("traceback"):
            parts.append(f"\n## Traceback\n```\n{incident['traceback']}\n```")

        if incident.get("sql_error"):
            parts.append(f"\n## SQL Error\n```sql\n{incident['sql_error']}\n```")

        if incident.get("dag_source"):
            parts.append(f"\n## DAG Source Code\n```python\n{incident['dag_source'][:3000]}\n```")

        if incident.get("task_source"):
            parts.append(f"\n## Failed Task Function\n```python\n{incident['task_source']}\n```")

        if incident.get("referenced_files"):
            for ref in incident["referenced_files"][:3]:
                parts.append(
                    f"\n## Referenced File: {ref['path']}\n```{ref['type']}\n{ref['content'][:1000]}\n```"
                )

        return "\n".join(parts)

    @staticmethod
    def _build_patch_system_prompt() -> str:
        return """You are DataSight AI, a code remediation engine for Apache Airflow.
Given a diagnosis and source code, generate the MINIMAL code change to fix the issue.

Rules:
1. Make the smallest possible change
2. Do NOT rewrite the entire file
3. Preserve all existing functionality
4. Add comments explaining the fix

Respond in this exact format:
DESCRIPTION: [what the patch does]
RISK_LEVEL: [low|medium|high]
PATCHED_CODE:
```python
[the complete fixed file]
```"""

    @staticmethod
    def _build_patch_user_prompt(diagnosis: Diagnosis, source_code: str) -> str:
        return f"""# Fix Request

## Diagnosis
**Root Cause:** {diagnosis.root_cause}
**Explanation:** {diagnosis.explanation}

## Current Source Code
```python
{source_code}
```

Generate the minimal fix for this issue."""

    # ── Response Parsing ─────────────────────────────────────────────

    @staticmethod
    def _parse_diagnosis(response: str, error_type: str) -> Diagnosis:
        """Parse the structured diagnosis from the LLM response."""
        import re

        root_cause = ""
        explanation = ""
        severity = "medium"
        confidence = 0.5

        rc_match = re.search(r"ROOT_CAUSE:\s*(.+?)(?:\n|$)", response)
        if rc_match:
            root_cause = rc_match.group(1).strip()

        exp_match = re.search(r"EXPLANATION:\s*(.+?)(?:SEVERITY:|CONFIDENCE:|$)", response, re.DOTALL)
        if exp_match:
            explanation = exp_match.group(1).strip()

        sev_match = re.search(r"SEVERITY:\s*(low|medium|high|critical)", response, re.IGNORECASE)
        if sev_match:
            severity = sev_match.group(1).lower()

        conf_match = re.search(r"CONFIDENCE:\s*(-?[\d.]+)", response)
        if conf_match:
            try:
                confidence = min(1.0, max(0.0, float(conf_match.group(1))))
            except ValueError:
                pass

        # Fallback if structured parsing failed
        if not root_cause:
            root_cause = response[:200]
            explanation = response

        return Diagnosis(
            root_cause=root_cause,
            explanation=explanation,
            severity=severity,
            error_type=error_type,
            confidence=confidence,
        )

    @staticmethod
    def _parse_patch(response: str, original_code: str, filepath: str) -> Optional[Patch]:
        """Parse the structured patch from the LLM response."""
        import re
        import difflib

        desc_match = re.search(r"DESCRIPTION:\s*(.+?)(?:\n|$)", response)
        description = desc_match.group(1).strip() if desc_match else "AI-generated fix"

        risk_match = re.search(r"RISK_LEVEL:\s*(low|medium|high)", response, re.IGNORECASE)
        risk_level = risk_match.group(1).lower() if risk_match else "medium"

        code_match = re.search(r"```python\n(.*?)```", response, re.DOTALL)
        if not code_match:
            return None

        patched_code = code_match.group(1).strip()

        # Generate unified diff
        diff = "\n".join(
            difflib.unified_diff(
                original_code.splitlines(),
                patched_code.splitlines(),
                fromfile=f"a/{filepath}",
                tofile=f"b/{filepath}",
                lineterm="",
            )
        )

        if not diff:
            return None

        return Patch(
            filepath=filepath,
            original_code=original_code,
            patched_code=patched_code,
            diff=diff,
            description=description,
            risk_level=risk_level,
        )
