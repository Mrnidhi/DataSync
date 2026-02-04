"""DataSight observability — Prometheus metrics & structured logging."""

from datasight.observability.metrics import (
    datasync_failures_detected,
    datasync_incident_status,
    datasync_patches_applied,
    datasync_patches_proposed,
    datasync_patches_rolled_back,
    datasync_rcas_run,
    datasync_time_to_diagnose,
    datasync_time_to_patch,
    record_failure_detected,
    record_patch_applied,
    record_rca_run,
)

__all__ = [
    "datasync_failures_detected",
    "datasync_incident_status",
    "datasync_patches_applied",
    "datasync_patches_proposed",
    "datasync_patches_rolled_back",
    "datasync_rcas_run",
    "datasync_time_to_diagnose",
    "datasync_time_to_patch",
    "record_failure_detected",
    "record_patch_applied",
    "record_rca_run",
]
