"""
DataSight Approval Gateway — orchestrates the approval workflow.

Manages the lifecycle of incidents from detection through diagnosis,
approval, patching, and verification. Dispatches notifications to
configured channels (UI, Slack, GitHub PR).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

from datasight.approval.models import Incident, IncidentStatus, PatchProposal
from datasight.config.settings import ApprovalChannel, get_settings
from datasight.observability.metrics import (
    datasync_patches_proposed,
    datasync_time_to_diagnose,
    datasync_time_to_patch,
    record_duration,
    record_patch_applied,
    record_rca_run,
)

logger = logging.getLogger("datasight.approval")


class ApprovalGateway:
    """
    Central coordinator for the incident approval workflow.

    Responsibilities:
    - Store and retrieve incidents
    - Coordinate the diagnosis → approval → patch pipeline
    - Dispatch notifications to configured channels
    """

    def __init__(self) -> None:
        settings = get_settings()
        self.approval_required = settings.approval_required
        self.channels = settings.approval_channels
        self.timeout_minutes = settings.approval_timeout_minutes
        self._store_dir = "/tmp/datasight/incidents"
        os.makedirs(self._store_dir, exist_ok=True)

    def create_incident(self, data: Dict) -> Incident:
        """Create a new incident from listener data and begin processing."""
        incident = Incident(
            dag_id=data.get("dag_id", ""),
            task_id=data.get("task_id", ""),
            run_id=data.get("run_id", ""),
            try_number=data.get("try_number", 1),
            execution_date=data.get("execution_date", ""),
            error_message=data.get("error_message", ""),
            traceback=data.get("traceback", ""),
            log_snippet=data.get("log_snippet", ""),
            dag_source=data.get("dag_source", ""),
            dag_filepath=data.get("dag_filepath", ""),
            task_source=data.get("task_source", ""),
            referenced_files=data.get("referenced_files", []),
        )

        logger.info("Incident %s created for %s.%s", incident.id, incident.dag_id, incident.task_id)
        self._save(incident)
        return incident

    def process_incident(self, incident: Incident) -> Incident:
        """
        Run the full diagnostic pipeline on an incident.

        1. Diagnose with LLM
        2. Generate patch
        3. Submit for approval (or auto-apply if approval_required=False)
        """
        # Step 1: Diagnose
        incident.update_status(IncidentStatus.DIAGNOSING)
        self._save(incident)

        try:
            from datasight.llm.engine import LLMEngine

            engine = LLMEngine()
            analysis = engine.analyze_incident(incident.to_dict())

            incident.root_cause = analysis.diagnosis.root_cause
            incident.explanation = analysis.diagnosis.explanation
            incident.severity = analysis.diagnosis.severity
            incident.confidence = analysis.diagnosis.confidence
            incident.error_type = analysis.diagnosis.error_type
            incident.model_used = analysis.model_used

            # Convert LLM patches to PatchProposals
            for patch in analysis.patches:
                proposal = PatchProposal(
                    filepath=patch.filepath,
                    diff=patch.diff,
                    description=patch.description,
                    patched_code=patch.patched_code,
                    risk_level=patch.risk_level,
                )
                incident.patches.append(proposal)
                datasync_patches_proposed.labels(risk_level=proposal.risk_level).inc()

            # Record diagnosis duration and RCA counter
            record_duration(incident.created_at, datasync_time_to_diagnose)
            record_rca_run(provider=analysis.model_used or "unknown", error_type=incident.error_type)

        except Exception as e:
            logger.error("Diagnosis failed: %s", e, exc_info=True)
            incident.update_status(IncidentStatus.FAILED)
            incident.error_message = f"Diagnosis error: {e}"
            self._save(incident)
            return incident

        # Step 2: Submit for approval
        if incident.patches:
            if self.approval_required:
                incident.update_status(IncidentStatus.AWAITING_APPROVAL)
                self._notify_channels(incident)
            else:
                incident.update_status(IncidentStatus.APPROVED)
                incident.approved_by = "auto"
                self._apply_patches(incident)
        else:
            # No patches generated — diagnosis only
            incident.update_status(IncidentStatus.AWAITING_APPROVAL)
            self._notify_channels(incident)

        self._save(incident)
        return incident

    def approve(self, incident_id: str, approved_by: str = "engineer") -> Optional[Incident]:
        """Approve an incident's patches for application."""
        incident = self.get_incident(incident_id)
        if not incident:
            logger.warning("Incident %s not found", incident_id)
            return None

        from datetime import datetime, timezone

        incident.update_status(IncidentStatus.APPROVED)
        incident.approved_by = approved_by
        incident.approved_at = datetime.now(timezone.utc).isoformat()

        self._apply_patches(incident)
        self._save(incident)
        return incident

    def reject(self, incident_id: str, reason: str = "") -> Optional[Incident]:
        """Reject an incident's patches."""
        incident = self.get_incident(incident_id)
        if not incident:
            return None

        incident.update_status(IncidentStatus.REJECTED)
        incident.rejection_reason = reason
        self._save(incident)
        return incident

    def get_incident(self, incident_id: str) -> Optional[Incident]:
        """Retrieve an incident by ID."""
        filepath = Path(self._store_dir) / f"{incident_id}.json"
        if not filepath.exists():
            return None

        with open(filepath) as f:
            data = json.load(f)

        return self._dict_to_incident(data)

    def list_incidents(self, status: Optional[IncidentStatus] = None) -> List[Incident]:
        """List all incidents, optionally filtered by status."""
        incidents = []
        store_path = Path(self._store_dir)

        for filepath in sorted(store_path.glob("*.json"), reverse=True):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                incident = self._dict_to_incident(data)
                if status is None or incident.status == status:
                    incidents.append(incident)
            except Exception as e:
                logger.debug("Could not load %s: %s", filepath, e)

        return incidents

    def _apply_patches(self, incident: Incident) -> None:
        """Apply approved patches to the codebase."""
        incident.update_status(IncidentStatus.PATCHING)

        settings = get_settings()

        for patch in incident.patches:
            try:
                from datasight.remediation.patcher import Patcher

                patcher = Patcher()
                patcher.apply(patch.filepath, patch.patched_code)

                logger.info("Patch %s applied to %s", patch.id, patch.filepath)

                # If Git is enabled, commit the change
                if settings.git_enabled:
                    from datasight.git.git_client import GitClient

                    git = GitClient()
                    git.commit_fix(
                        filepath=patch.filepath,
                        message=f"datasight: fix {incident.dag_id}.{incident.task_id} — {patch.description}",
                        branch=f"{settings.git_branch_prefix}/{incident.dag_id}-{incident.id}",
                    )

                record_patch_applied(result="success")

            except Exception as e:
                logger.error("Failed to apply patch %s: %s", patch.id, e)
                record_patch_applied(result="failure")
                incident.update_status(IncidentStatus.FAILED)
                return

        incident.update_status(IncidentStatus.PATCHED)
        record_duration(incident.created_at, datasync_time_to_patch)

    def _notify_channels(self, incident: Incident) -> None:
        """Send notifications via configured channels."""
        for channel in self.channels:
            try:
                if channel == ApprovalChannel.SLACK:
                    from datasight.approval.channels.slack import send_slack_notification
                    send_slack_notification(incident)
                elif channel == ApprovalChannel.GITHUB_PR:
                    from datasight.approval.channels.github_pr import create_github_pr
                    create_github_pr(incident)
                elif channel == ApprovalChannel.UI:
                    # UI channel is passive — incidents are stored and displayed
                    logger.info("Incident %s available in UI dashboard", incident.id)
            except Exception as e:
                logger.error("Failed to notify channel %s: %s", channel.value, e)

    def _save(self, incident: Incident) -> None:
        """Persist an incident to disk."""
        filepath = Path(self._store_dir) / f"{incident.id}.json"
        with open(filepath, "w") as f:
            json.dump(incident.to_dict(), f, indent=2, default=str)

    @staticmethod
    def _dict_to_incident(data: dict) -> Incident:
        """Reconstruct an Incident from a saved dict."""
        patches = [
            PatchProposal(
                id=p.get("id", ""),
                filepath=p.get("filepath", ""),
                diff=p.get("diff", ""),
                description=p.get("description", ""),
                risk_level=p.get("risk_level", "low"),
            )
            for p in data.get("patches", [])
        ]

        return Incident(
            id=data.get("id", ""),
            status=IncidentStatus(data.get("status", "detected")),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            dag_id=data.get("dag_id", ""),
            task_id=data.get("task_id", ""),
            run_id=data.get("run_id", ""),
            try_number=data.get("try_number", 1),
            execution_date=data.get("execution_date", ""),
            error_message=data.get("error_message", ""),
            traceback=data.get("traceback", ""),
            error_type=data.get("error_type", "unknown"),
            root_cause=data.get("root_cause", ""),
            explanation=data.get("explanation", ""),
            severity=data.get("severity", "medium"),
            confidence=data.get("confidence", 0.0),
            model_used=data.get("model_used", ""),
            patches=patches,
            approved_by=data.get("approved_by"),
            approved_at=data.get("approved_at"),
        )
