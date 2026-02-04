"""
Prometheus metrics for DataSync.

These counters and histograms underpin the MTTR claims in docs/metrics.md.
The /metrics endpoint exposed by datasight.api.app is what kube-prometheus
or any standard Prometheus server scrapes.

Naming convention: `datasync_<noun>_<unit>` for counters and histograms.
Labels are kept low-cardinality to avoid Prometheus blowing up.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

logger = logging.getLogger("datasight.metrics")

# A dedicated registry keeps DataSync metrics isolated from any process-default
# metrics that other libraries may register.
REGISTRY: CollectorRegistry = CollectorRegistry()

# --- Counters ---------------------------------------------------------------

datasync_failures_detected = Counter(
    "datasync_failures_detected_total",
    "Airflow task failures observed by the DataSight listener.",
    labelnames=("dag_id",),
    registry=REGISTRY,
)

datasync_rcas_run = Counter(
    "datasync_rcas_run_total",
    "Root-cause analyses produced by the LLM engine.",
    labelnames=("provider", "error_type"),
    registry=REGISTRY,
)

datasync_patches_proposed = Counter(
    "datasync_patches_proposed_total",
    "Patches proposed by the LLM engine, by risk level.",
    labelnames=("risk_level",),
    registry=REGISTRY,
)

datasync_patches_applied = Counter(
    "datasync_patches_applied_total",
    "Patches applied to the codebase, by result.",
    labelnames=("result",),  # success | failure
    registry=REGISTRY,
)

datasync_patches_rolled_back = Counter(
    "datasync_patches_rolled_back_total",
    "Patches rolled back after failure or engineer rejection.",
    registry=REGISTRY,
)

# --- Histograms (durations in seconds) -------------------------------------

# 1s, 5s, 15s, 30s, 1m, 2m, 5m, 10m, 30m, 1h
DURATION_BUCKETS = (1.0, 5.0, 15.0, 30.0, 60.0, 120.0, 300.0, 600.0, 1800.0, 3600.0)

datasync_time_to_diagnose = Histogram(
    "datasync_time_to_diagnose_seconds",
    "Wall time from incident creation to LLM diagnosis completion.",
    buckets=DURATION_BUCKETS,
    registry=REGISTRY,
)

datasync_time_to_patch = Histogram(
    "datasync_time_to_patch_seconds",
    "Wall time from incident creation to patch applied (MTTR proxy).",
    buckets=DURATION_BUCKETS,
    registry=REGISTRY,
)

# --- Gauge ------------------------------------------------------------------

datasync_incident_status = Gauge(
    "datasync_incidents_in_state",
    "Number of incidents currently in each lifecycle state.",
    labelnames=("status",),
    registry=REGISTRY,
)


# --- Recording helpers ------------------------------------------------------


def record_failure_detected(dag_id: str) -> None:
    """Increment the failure counter for a DAG."""
    datasync_failures_detected.labels(dag_id=dag_id or "unknown").inc()


def record_rca_run(provider: str, error_type: str) -> None:
    """Increment the RCA counter when the LLM engine produces a diagnosis."""
    datasync_rcas_run.labels(
        provider=provider or "unknown",
        error_type=error_type or "unknown",
    ).inc()


def record_patch_applied(result: str) -> None:
    """Increment the patch-applied counter with result=success|failure."""
    datasync_patches_applied.labels(result=result).inc()


def record_duration(start_iso: str, observer: Histogram) -> Optional[float]:
    """Compute now - start_iso (in seconds) and observe it on the histogram."""
    if not start_iso:
        return None
    try:
        start = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
    except ValueError:
        logger.debug("record_duration: could not parse %s", start_iso)
        return None
    now = datetime.now(timezone.utc)
    delta = (now - start).total_seconds()
    if delta < 0:
        delta = 0.0
    observer.observe(delta)
    return delta
