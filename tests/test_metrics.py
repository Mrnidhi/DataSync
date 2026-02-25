"""Tests for datasight.observability.metrics."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from prometheus_client import generate_latest

from datasight.observability.metrics import (
    REGISTRY,
    datasync_time_to_diagnose,
    record_duration,
    record_failure_detected,
    record_patch_applied,
    record_rca_run,
)


def _scrape() -> str:
    return generate_latest(REGISTRY).decode()


@pytest.mark.unit
def test_record_failure_detected_increments_counter():
    before = _scrape()
    record_failure_detected("dag_alpha")
    after = _scrape()
    assert "datasync_failures_detected_total" in after
    # The counter line should appear with our label
    assert 'dag_id="dag_alpha"' in after
    # And it should have grown
    assert after != before


@pytest.mark.unit
def test_record_rca_run_uses_low_cardinality_labels():
    record_rca_run(provider="openai", error_type="ValueError")
    body = _scrape()
    assert 'provider="openai"' in body
    assert 'error_type="ValueError"' in body


@pytest.mark.unit
def test_record_patch_applied_success_and_failure():
    record_patch_applied(result="success")
    record_patch_applied(result="failure")
    body = _scrape()
    assert 'result="success"' in body
    assert 'result="failure"' in body


@pytest.mark.unit
def test_record_duration_observes_positive_seconds():
    five_seconds_ago = (datetime.now(timezone.utc) - timedelta(seconds=5)).isoformat()
    delta = record_duration(five_seconds_ago, datasync_time_to_diagnose)
    assert delta is not None
    assert 4.5 <= delta <= 30  # generous upper bound for slow CI


@pytest.mark.unit
def test_record_duration_handles_bad_input():
    assert record_duration("", datasync_time_to_diagnose) is None
    assert record_duration("not-an-iso-string", datasync_time_to_diagnose) is None


@pytest.mark.unit
def test_record_duration_clamps_negative_to_zero():
    """Clock skew should not produce negative observations."""
    future = (datetime.now(timezone.utc) + timedelta(seconds=10)).isoformat()
    delta = record_duration(future, datasync_time_to_diagnose)
    assert delta == 0.0
