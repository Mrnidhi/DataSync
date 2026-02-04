"""
DataSync REST API — FastAPI application.

Exposes:
  GET  /healthz                  liveness probe
  GET  /readyz                   readiness probe
  GET  /metrics                  Prometheus exposition endpoint
  GET  /v1/incidents             list incidents (optional ?status=)
  GET  /v1/incidents/{id}        fetch a single incident
  POST /v1/incidents/{id}/approve  engineer approves the proposed patches
  POST /v1/incidents/{id}/reject   engineer rejects with optional reason
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from datasight.approval.gateway import ApprovalGateway
from datasight.approval.models import IncidentStatus
from datasight.config.settings import get_settings
from datasight.observability.metrics import REGISTRY, datasync_incident_status

logger = logging.getLogger("datasight.api")


class IncidentSummary(BaseModel):
    id: str
    status: str
    dag_id: str
    task_id: str
    severity: str
    confidence: float
    created_at: str
    updated_at: str
    error_type: str
    patches: int


class RejectBody(BaseModel):
    reason: str = ""


class ApproveBody(BaseModel):
    approved_by: str = "engineer"


def create_app() -> FastAPI:
    """Application factory — also used by tests."""
    settings = get_settings()

    app = FastAPI(
        title="DataSync API",
        description="Self-Healing Airflow Observability Platform",
        version="0.1.0",
    )

    gateway = ApprovalGateway()

    @app.get("/healthz", tags=["health"])
    def healthz() -> dict:
        return {"status": "ok", "enabled": settings.enabled}

    @app.get("/readyz", tags=["health"])
    def readyz() -> dict:
        return {"status": "ready"}

    @app.get("/metrics", tags=["observability"])
    def metrics() -> Response:
        # Refresh status gauge before each scrape so it reflects on-disk state.
        _refresh_status_gauge(gateway)
        payload = generate_latest(REGISTRY)
        return Response(content=payload, media_type=CONTENT_TYPE_LATEST)

    @app.get("/v1/incidents", response_model=List[IncidentSummary], tags=["incidents"])
    def list_incidents(
        status: Optional[str] = Query(default=None, description="Filter by status"),
    ) -> List[IncidentSummary]:
        status_filter = _parse_status(status) if status else None
        incidents = gateway.list_incidents(status=status_filter)
        return [_summarize(i) for i in incidents]

    @app.get("/v1/incidents/{incident_id}", tags=["incidents"])
    def get_incident(incident_id: str) -> dict:
        incident = gateway.get_incident(incident_id)
        if not incident:
            raise HTTPException(status_code=404, detail="incident not found")
        return incident.to_dict()

    @app.post("/v1/incidents/{incident_id}/approve", tags=["incidents"])
    def approve(incident_id: str, body: ApproveBody) -> dict:
        incident = gateway.approve(incident_id, approved_by=body.approved_by)
        if not incident:
            raise HTTPException(status_code=404, detail="incident not found")
        return incident.to_dict()

    @app.post("/v1/incidents/{incident_id}/reject", tags=["incidents"])
    def reject(incident_id: str, body: RejectBody) -> dict:
        incident = gateway.reject(incident_id, reason=body.reason)
        if not incident:
            raise HTTPException(status_code=404, detail="incident not found")
        return incident.to_dict()

    return app


def _parse_status(value: str) -> IncidentStatus:
    try:
        return IncidentStatus(value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid status: {value}") from exc


def _summarize(incident) -> IncidentSummary:
    return IncidentSummary(
        id=incident.id,
        status=incident.status.value,
        dag_id=incident.dag_id,
        task_id=incident.task_id,
        severity=incident.severity,
        confidence=incident.confidence,
        created_at=incident.created_at,
        updated_at=incident.updated_at,
        error_type=incident.error_type,
        patches=len(incident.patches),
    )


def _refresh_status_gauge(gateway: ApprovalGateway) -> None:
    """Reset the status gauge to current counts on disk."""
    counts: dict[str, int] = {s.value: 0 for s in IncidentStatus}
    for incident in gateway.list_incidents():
        counts[incident.status.value] = counts.get(incident.status.value, 0) + 1
    for status, n in counts.items():
        datasync_incident_status.labels(status=status).set(n)


# Module-level instance so `uvicorn datasight.api.app:app` works.
app = create_app()
