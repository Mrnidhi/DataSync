"""Tests for datasight.api.app."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch):
    """Build an API client with a clean isolated incident store."""
    tmp = tempfile.mkdtemp(prefix="datasync-api-test-")

    # Patch the gateway store dir before app construction.
    from datasight.approval import gateway as gateway_module

    original_init = gateway_module.ApprovalGateway.__init__

    def patched_init(self):
        original_init(self)
        self._store_dir = tmp
        Path(tmp).mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(gateway_module.ApprovalGateway, "__init__", patched_init)

    from datasight.api.app import create_app

    app = create_app()
    with TestClient(app) as client:
        yield client

    shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.unit
def test_healthz(api_client):
    r = api_client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.unit
def test_readyz(api_client):
    r = api_client.get("/readyz")
    assert r.status_code == 200


@pytest.mark.unit
def test_metrics_exposes_prometheus_text(api_client):
    r = api_client.get("/metrics")
    assert r.status_code == 200
    assert "text/plain" in r.headers["content-type"]
    body = r.text
    # Our custom metrics should be in the exposition output
    assert "datasync_failures_detected_total" in body
    assert "datasync_time_to_diagnose_seconds" in body
    assert "datasync_incidents_in_state" in body


@pytest.mark.unit
def test_list_incidents_empty_returns_empty_array(api_client):
    r = api_client.get("/v1/incidents")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.unit
def test_list_incidents_invalid_status_returns_400(api_client):
    r = api_client.get("/v1/incidents?status=bogus_state")
    assert r.status_code == 400


@pytest.mark.unit
def test_get_incident_unknown_returns_404(api_client):
    r = api_client.get("/v1/incidents/nonexistent")
    assert r.status_code == 404


@pytest.mark.unit
def test_approve_unknown_returns_404(api_client):
    r = api_client.post("/v1/incidents/nope/approve", json={"approved_by": "alice"})
    assert r.status_code == 404


@pytest.mark.unit
def test_reject_unknown_returns_404(api_client):
    r = api_client.post("/v1/incidents/nope/reject", json={"reason": "no thanks"})
    assert r.status_code == 404
