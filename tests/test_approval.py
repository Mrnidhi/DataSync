"""Tests for datasight.approval (models + gateway)"""

import json
import os
import shutil
import tempfile

import pytest

from datasight.approval.models import Incident, IncidentStatus, PatchProposal
from datasight.approval.gateway import ApprovalGateway


class TestIncidentModel:
    """Test the Incident data model."""

    def test_create_incident(self):
        """Should create an incident with defaults."""
        inc = Incident(dag_id="test_dag", task_id="test_task")
        assert inc.dag_id == "test_dag"
        assert inc.task_id == "test_task"
        assert inc.status == IncidentStatus.DETECTED
        assert inc.id != ""
        assert inc.created_at != ""

    def test_update_status(self):
        """Should transition and update timestamps."""
        inc = Incident()
        old_updated = inc.updated_at
        inc.update_status(IncidentStatus.DIAGNOSING)
        assert inc.status == IncidentStatus.DIAGNOSING
        # updated_at should change (or be at least equal for very fast tests)
        assert inc.updated_at >= old_updated

    def test_to_dict(self):
        """Should serialize to a dict."""
        inc = Incident(dag_id="d1", task_id="t1", root_cause="test cause")
        d = inc.to_dict()
        assert d["dag_id"] == "d1"
        assert d["task_id"] == "t1"
        assert d["root_cause"] == "test cause"
        assert d["status"] == "detected"

    def test_to_dict_with_patches(self):
        """Should serialize patches correctly."""
        inc = Incident()
        inc.patches.append(PatchProposal(
            filepath="dag.py", diff="- old\n+ new", description="fix"
        ))
        d = inc.to_dict()
        assert len(d["patches"]) == 1
        assert d["patches"][0]["filepath"] == "dag.py"

    def test_all_statuses(self):
        """All status values should be valid."""
        statuses = [
            IncidentStatus.DETECTED, IncidentStatus.DIAGNOSING,
            IncidentStatus.AWAITING_APPROVAL, IncidentStatus.APPROVED,
            IncidentStatus.REJECTED, IncidentStatus.PATCHING,
            IncidentStatus.PATCHED, IncidentStatus.VERIFIED,
            IncidentStatus.FAILED,
        ]
        assert len(statuses) == 9
        for s in statuses:
            assert isinstance(s.value, str)


class TestPatchProposal:
    """Test the PatchProposal model."""

    def test_create_patch(self):
        """Should create with auto-generated ID."""
        p = PatchProposal(filepath="dag.py", diff="some diff")
        assert p.id != ""
        assert p.filepath == "dag.py"
        assert p.risk_level == "low"


class TestApprovalGateway:
    """Test the Approval Gateway lifecycle."""

    def setup_method(self):
        """Create a temp store directory."""
        from datasight.config.settings import get_settings
        get_settings.cache_clear()

        self.temp_dir = tempfile.mkdtemp()

    def teardown_method(self):
        """Clean up."""
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _make_gateway(self) -> ApprovalGateway:
        gw = ApprovalGateway()
        gw._store_dir = self.temp_dir
        return gw

    def test_create_incident(self):
        """Should create and persist an incident."""
        gw = self._make_gateway()
        inc = gw.create_incident({
            "dag_id": "test_dag",
            "task_id": "test_task",
            "traceback": "some error",
        })
        assert inc.dag_id == "test_dag"
        assert inc.status == IncidentStatus.DETECTED

        # Should be persisted to disk
        filepath = os.path.join(self.temp_dir, f"{inc.id}.json")
        assert os.path.exists(filepath)

    def test_get_incident(self):
        """Should retrieve a persisted incident."""
        gw = self._make_gateway()
        inc = gw.create_incident({"dag_id": "d1", "task_id": "t1"})

        loaded = gw.get_incident(inc.id)
        assert loaded is not None
        assert loaded.dag_id == "d1"
        assert loaded.task_id == "t1"

    def test_get_nonexistent_incident(self):
        """Should return None for missing incidents."""
        gw = self._make_gateway()
        assert gw.get_incident("nonexistent") is None

    def test_list_incidents(self):
        """Should list all stored incidents."""
        gw = self._make_gateway()
        gw.create_incident({"dag_id": "d1", "task_id": "t1"})
        gw.create_incident({"dag_id": "d2", "task_id": "t2"})

        incidents = gw.list_incidents()
        assert len(incidents) == 2

    def test_list_incidents_filtered(self):
        """Should filter by status."""
        gw = self._make_gateway()
        inc1 = gw.create_incident({"dag_id": "d1", "task_id": "t1"})
        inc2 = gw.create_incident({"dag_id": "d2", "task_id": "t2"})

        # Manually change status of one
        inc2.update_status(IncidentStatus.AWAITING_APPROVAL)
        gw._save(inc2)

        detected = gw.list_incidents(status=IncidentStatus.DETECTED)
        awaiting = gw.list_incidents(status=IncidentStatus.AWAITING_APPROVAL)
        assert len(detected) == 1
        assert len(awaiting) == 1

    def test_reject_incident(self):
        """Should reject and record reason."""
        gw = self._make_gateway()
        inc = gw.create_incident({"dag_id": "d1", "task_id": "t1"})

        result = gw.reject(inc.id, reason="Not a real fix")
        assert result is not None
        assert result.status == IncidentStatus.REJECTED
        assert result.rejection_reason == "Not a real fix"

    def test_reject_nonexistent(self):
        """Should return None for rejecting missing incidents."""
        gw = self._make_gateway()
        assert gw.reject("nonexistent") is None
