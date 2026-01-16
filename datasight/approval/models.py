"""
DataSight Approval Models — data structures for incidents, patches, and approvals.

These models represent the core state machine:
  DETECTED → DIAGNOSING → AWAITING_APPROVAL → APPROVED/REJECTED → PATCHED → VERIFIED
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from dataclasses import dataclass, field


class IncidentStatus(str, Enum):
    DETECTED = "detected"
    DIAGNOSING = "diagnosing"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PATCHING = "patching"
    PATCHED = "patched"
    VERIFIED = "verified"
    FAILED = "failed"


@dataclass
class PatchProposal:
    """A proposed code change for engineer review."""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    filepath: str = ""
    diff: str = ""
    description: str = ""
    patched_code: str = ""
    risk_level: str = "low"


@dataclass
class Incident:
    """
    Represents a single task failure and its diagnostic lifecycle.

    This is the central domain object that flows through the entire pipeline:
    Listener → Analyzer → LLM → Approval → Patcher
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    status: IncidentStatus = IncidentStatus.DETECTED
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Airflow context
    dag_id: str = ""
    task_id: str = ""
    run_id: str = ""
    try_number: int = 1
    execution_date: str = ""

    # Analysis results
    error_message: str = ""
    traceback: str = ""
    log_snippet: str = ""
    sql_error: Optional[str] = None
    error_type: str = "unknown"

    # Code context
    dag_source: str = ""
    dag_filepath: str = ""
    task_source: str = ""
    referenced_files: List[dict] = field(default_factory=list)

    # Diagnosis
    root_cause: str = ""
    explanation: str = ""
    severity: str = "medium"
    confidence: float = 0.0
    model_used: str = ""

    # Patch proposals
    patches: List[PatchProposal] = field(default_factory=list)

    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[str] = None
    rejection_reason: Optional[str] = None

    def update_status(self, new_status: IncidentStatus) -> None:
        """Transition the incident to a new status."""
        self.status = new_status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Serialize to a dict for JSON storage."""
        return {
            "id": self.id,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "dag_id": self.dag_id,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "try_number": self.try_number,
            "execution_date": self.execution_date,
            "error_message": self.error_message,
            "traceback": self.traceback[:500],
            "error_type": self.error_type,
            "root_cause": self.root_cause,
            "explanation": self.explanation,
            "severity": self.severity,
            "confidence": self.confidence,
            "model_used": self.model_used,
            "patches": [
                {"id": p.id, "filepath": p.filepath, "diff": p.diff,
                 "description": p.description, "risk_level": p.risk_level}
                for p in self.patches
            ],
            "approved_by": self.approved_by,
            "approved_at": self.approved_at,
        }
