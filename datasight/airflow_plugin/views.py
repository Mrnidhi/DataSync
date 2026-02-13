"""
DataSight Airflow Views — Flask Blueprint served within the Airflow Web UI.

Provides:
  /datasight/           → Monitoring dashboard
  /datasight/incidents  → List of incidents
  /datasight/approve    → Approve a patch (POST)
  /datasight/reject     → Reject a patch (POST)
"""

from __future__ import annotations

import json
import logging

from flask import Blueprint, Response, request

logger = logging.getLogger("datasight.airflow_plugin.views")

datasight_blueprint = Blueprint(
    "datasight",
    __name__,
    url_prefix="/datasight",
)


@datasight_blueprint.route("/")
def dashboard():
    """Main DataSight monitoring dashboard embedded in Airflow."""
    from datasight.approval.gateway import ApprovalGateway

    gateway = ApprovalGateway()
    incidents = gateway.list_incidents()

    severity_colors = {
        "low": "#4CAF50", "medium": "#FF9800",
        "high": "#f44336", "critical": "#9C27B0",
    }
    status_icons = {
        "detected": "🔵", "diagnosing": "⏳", "awaiting_approval": "🟡",
        "approved": "🟢", "rejected": "🔴", "patching": "🔧",
        "patched": "✅", "verified": "✨", "failed": "💥",
    }

    rows = ""
    for inc in incidents[:20]:
        icon = status_icons.get(inc.status.value, "⚪")
        color = severity_colors.get(inc.severity, "#999")
        actions = ""
        if inc.status.value == "awaiting_approval":
            actions = f"""
                <form method="POST" action="/datasight/approve" style="display:inline">
                    <input type="hidden" name="incident_id" value="{inc.id}">
                    <button type="submit" style="background:#4CAF50;color:white;border:none;padding:6px 16px;border-radius:4px;cursor:pointer">✅ Approve</button>
                </form>
                <form method="POST" action="/datasight/reject" style="display:inline;margin-left:8px">
                    <input type="hidden" name="incident_id" value="{inc.id}">
                    <button type="submit" style="background:#f44336;color:white;border:none;padding:6px 16px;border-radius:4px;cursor:pointer">❌ Reject</button>
                </form>
            """

        rows += f"""
        <tr>
            <td>{icon} {inc.status.value}</td>
            <td><code>{inc.dag_id}</code></td>
            <td><code>{inc.task_id}</code></td>
            <td><span style="color:{color};font-weight:bold">{inc.severity.upper()}</span></td>
            <td>{inc.root_cause[:60] + '...' if len(inc.root_cause) > 60 else inc.root_cause}</td>
            <td>{inc.confidence:.0%}</td>
            <td>{actions}</td>
            <td style="font-size:12px;color:#888">{inc.created_at[:19]}</td>
        </tr>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>DataSight AI Dashboard</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1a2e; color: #eee; padding: 30px; }}
            h1 {{ color: #00d2ff; }}
            table {{ width: 100%; border-collapse: collapse; background: #16213e; border-radius: 8px; overflow: hidden; }}
            th {{ background: #0f3460; padding: 12px; text-align: left; font-size: 13px; text-transform: uppercase; letter-spacing: 1px; }}
            td {{ padding: 12px; border-bottom: 1px solid #1a1a2e; font-size: 14px; }}
            tr:hover {{ background: #1a1a3e; }}
            code {{ background: #0f3460; padding: 2px 6px; border-radius: 3px; font-size: 13px; }}
            .header {{ display: flex; align-items: center; gap: 15px; margin-bottom: 25px; }}
            .stat {{ background: #16213e; padding: 20px; border-radius: 8px; text-align: center; min-width: 120px; }}
            .stat-value {{ font-size: 28px; font-weight: bold; color: #00d2ff; }}
            .stat-label {{ font-size: 12px; color: #888; margin-top: 5px; }}
            .stats {{ display: flex; gap: 15px; margin-bottom: 25px; }}
        </style>
        <meta http-equiv="refresh" content="30">
    </head>
    <body>
        <div class="header">
            <h1>🔬 DataSight AI</h1>
            <span style="color:#888">Self-Healing Observability</span>
        </div>

        <div class="stats">
            <div class="stat"><div class="stat-value">{len(incidents)}</div><div class="stat-label">Total Incidents</div></div>
            <div class="stat"><div class="stat-value">{len([i for i in incidents if i.status.value == 'awaiting_approval'])}</div><div class="stat-label">Awaiting Approval</div></div>
            <div class="stat"><div class="stat-value">{len([i for i in incidents if i.status.value == 'patched'])}</div><div class="stat-label">Auto-Fixed</div></div>
            <div class="stat"><div class="stat-value">{len([i for i in incidents if i.severity == 'critical'])}</div><div class="stat-label">Critical</div></div>
        </div>

        <table>
            <thead>
                <tr><th>Status</th><th>DAG</th><th>Task</th><th>Severity</th><th>Root Cause</th><th>Confidence</th><th>Actions</th><th>Time</th></tr>
            </thead>
            <tbody>
                {rows if rows else '<tr><td colspan="8" style="text-align:center;padding:40px;color:#888">No incidents detected yet. DataSight is monitoring your pipelines.</td></tr>'}
            </tbody>
        </table>
    </body>
    </html>
    """
    return Response(html, content_type="text/html")


@datasight_blueprint.route("/incidents")
def incidents_json():
    """JSON endpoint for all incidents."""
    from datasight.approval.gateway import ApprovalGateway

    gateway = ApprovalGateway()
    incidents = gateway.list_incidents()
    return Response(
        json.dumps([i.to_dict() for i in incidents], default=str),
        content_type="application/json",
    )


@datasight_blueprint.route("/approve", methods=["POST"])
def approve():
    """Approve a pending incident."""
    from datasight.approval.gateway import ApprovalGateway

    incident_id = request.form.get("incident_id") or request.json.get("incident_id", "")
    gateway = ApprovalGateway()
    incident = gateway.approve(incident_id, approved_by="airflow_ui")

    if incident:
        return Response(
            f'<script>alert("Patch approved for {incident.dag_id}.{incident.task_id}!");window.location="/datasight/";</script>',
            content_type="text/html",
        )
    return Response("Incident not found", status=404)


@datasight_blueprint.route("/reject", methods=["POST"])
def reject():
    """Reject a pending incident."""
    from datasight.approval.gateway import ApprovalGateway

    incident_id = request.form.get("incident_id") or request.json.get("incident_id", "")
    reason = request.form.get("reason", "") or request.json.get("reason", "Rejected by engineer")
    gateway = ApprovalGateway()
    incident = gateway.reject(incident_id, reason=reason)

    if incident:
        return Response(
            f'<script>alert("Patch rejected.");window.location="/datasight/";</script>',
            content_type="text/html",
        )
    return Response("Incident not found", status=404)
