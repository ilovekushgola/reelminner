"""Phase 3.6 — Performance Intelligence & Compute Monitoring tests.

Covers: capability detection (no PII), PerformanceStore round-trip + sample cap,
analyzer (worker comparison / diminishing returns / conservative bottleneck
labels), recommendation engine (Observed/Estimated/Insufficient-Data), settings
validation, the PerformanceService facade via ReelminnerApplication, job-end
recording, and the 6 MCP tool entry points. No UI / no auto-changes asserted.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import ReelminnerApplication
from performance import (
    detect_capabilities,
    PerformanceStore,
    PerformanceAnalyzer,
    RecommendationEngine,
    JobPerformanceSummary,
    JobPerformanceSample,
    BOTTLENECK_NETWORK_LIMITED,
    BOTTLENECK_MEMORY_BOUND,
    BOTTLENECK_UNKNOWN,
    CONF_LIKELY,
    CONF_UNKNOWN,
    BASIS_OBSERVED,
    BASIS_INSUFFICIENT,
)
from proxies import NetworkMode
from jobs import JobStatus
from settings import SettingsService
from storage import JobStore


# --------------------------------------------------------------------------- #
# Capabilities (PART 2)
# --------------------------------------------------------------------------- #
def test_capabilities_detected_without_pii():
    caps = detect_capabilities()
    assert caps.cpu_logical >= 0
    assert caps.total_ram_bytes > 0
    d = caps.to_dict()
    # Explicitly no personal / sensitive identifiers.
    for forbidden in ("hostname", "username", "user", "mac", "ip", "serial"):
        assert forbidden not in d, f"capability leak: {forbidden}"
    assert "gpu_available" in d


# --------------------------------------------------------------------------- #
# Store (PART 7 / 8)
# --------------------------------------------------------------------------- #
def test_store_summary_roundtrip():
    tmp = tempfile.mkdtemp()
    try:
        store = PerformanceStore(os.path.join(tmp, "p.db"))
        s = JobPerformanceSummary(
            job_id="j1", worker_count=3, delay=1.0, processed=10,
            successful=9, failed=1, blocked=0, rate_limited=0,
            elapsed_seconds=10.0, avg_urls_per_min=60.0,
        )
        store.save_job_summary(s)
        got = store.get_job_summary("j1")
        assert got is not None
        assert got.job_id == "j1"
        assert got.processed == 10
        assert got.avg_urls_per_min == 60.0
        # Overwrite (INSERT OR REPLACE) keeps a single row.
        store.save_job_summary(s)
        assert store.count_summaries("j1") == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_store_samples_capped():
    tmp = tempfile.mkdtemp()
    try:
        store = PerformanceStore(os.path.join(tmp, "p.db"))
        for i in range(150):
            store.add_job_sample(
                JobPerformanceSample(job_id="j1", timestamp=float(i), processed=i),
                max_per_job=100,
            )
        samples = store.get_job_samples("j1", limit=500)
        assert len(samples) == 100, "samples must be capped at max_per_job"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_store_config_outcome_and_history_survives_reload():
    tmp = tempfile.mkdtemp()
    try:
        db = os.path.join(tmp, "p.db")
        store = PerformanceStore(db)
        store.save_machine_profile(detect_capabilities())
        store.save_config_outcome(
            {
                "job_id": "j1", "workers": 3, "delay": 1.0,
                "network_mode": "direct", "proxy_id": None,
                "processed": 10, "successful": 9, "failed": 1,
                "elapsed_seconds": 10.0, "urls_per_min": 60.0,
            }
        )
        store.close()
        # Re-open -> data persists across restart.
        store2 = PerformanceStore(db)
        outs = store2.get_config_outcomes()
        assert len(outs) == 1
        assert outs[0]["workers"] == 3
        prof = store2.get_job_samples("j1", 1)
        # machine profile row exists
        with store2._lock:
            row = store2._conn.execute(
                "SELECT COUNT(*) AS c FROM perf_machine_profile"
            ).fetchone()
        assert row["c"] >= 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Analyzer (PART 9 / 10 / 11)
# --------------------------------------------------------------------------- #
OUTCOMES = [
    {"job_id": "a", "workers": 1, "delay": 1, "network_mode": "direct",
     "proxy_id": None, "processed": 10, "successful": 10, "failed": 0,
     "elapsed_seconds": 60, "urls_per_min": 10.0},
    {"job_id": "b", "workers": 2, "delay": 1, "network_mode": "direct",
     "proxy_id": None, "processed": 20, "successful": 20, "failed": 0,
     "elapsed_seconds": 60, "urls_per_min": 20.0},
    {"job_id": "c", "workers": 4, "delay": 1, "network_mode": "direct",
     "proxy_id": None, "processed": 40, "successful": 40, "failed": 0,
     "elapsed_seconds": 60, "urls_per_min": 22.0},
]


def test_analyzer_compare_workers():
    cmp = PerformanceAnalyzer.compare_workers(OUTCOMES)
    assert cmp[1]["mean_urls_per_min"] == 10.0
    assert cmp[2]["mean_urls_per_min"] == 20.0
    assert cmp[4]["mean_urls_per_min"] == 22.0


def test_analyzer_diminishing_returns_observed():
    cmp = PerformanceAnalyzer.compare_workers(OUTCOMES)
    safe, basis = PerformanceAnalyzer.diminishing_returns(cmp)
    assert basis == BASIS_OBSERVED
    assert safe <= 4


def test_analyzer_diminishing_returns_insufficient_with_one_level():
    cmp = PerformanceAnalyzer.compare_workers(OUTCOMES[:1])
    safe, basis = PerformanceAnalyzer.diminishing_returns(cmp)
    assert basis == "Estimated"
    assert safe == 1


def test_detect_bottleneck_network_likely():
    s = JobPerformanceSummary(job_id="x", processed=100, blocked=40, rate_limited=0)
    label, conf = PerformanceAnalyzer.detect_bottleneck(s, 10.0, 0, 16e9)
    assert label == BOTTLENECK_NETWORK_LIMITED
    assert conf == CONF_LIKELY


def test_detect_bottleneck_memory_possible():
    s = JobPerformanceSummary(job_id="x", processed=100, blocked=0, rate_limited=0)
    label, conf = PerformanceAnalyzer.detect_bottleneck(s, 10.0, 15e9, 16e9)
    assert label == BOTTLENECK_MEMORY_BOUND


def test_detect_bottleneck_unknown_when_clean():
    s = JobPerformanceSummary(job_id="x", processed=100, blocked=0, rate_limited=0)
    label, conf = PerformanceAnalyzer.detect_bottleneck(s, 10.0, 0, 16e9)
    assert label == BOTTLENECK_UNKNOWN
    assert conf == CONF_UNKNOWN


# --------------------------------------------------------------------------- #
# Recommendation engine (PART 12 / 13)
# --------------------------------------------------------------------------- #
def test_recommendation_insufficient_data():
    engine = RecommendationEngine(detect_capabilities())
    rec = engine.recommend_workers([])
    assert rec.basis == BASIS_INSUFFICIENT
    assert rec.suggested_workers is None
    assert "Insufficient" in rec.message


def test_recommendation_does_not_claim_causation():
    engine = RecommendationEngine(detect_capabilities())
    rec = engine.recommend_workers(OUTCOMES)
    assert rec.suggested_workers is not None
    assert rec.basis in (BASIS_OBSERVED, "Estimated")
    # Safe-language check: never asserts it changed anything.
    assert "recommendation only" in rec.message.lower()


# --------------------------------------------------------------------------- #
# Settings (PART 15)
# --------------------------------------------------------------------------- #
def test_settings_performance_section_defaults():
    tmp = tempfile.mkdtemp()
    try:
        svc = SettingsService(JobStore(Path(tmp) / "db.db"))
        assert svc.get().performance.sampling_interval == 5.0
        assert svc.get().performance.monitoring_enabled is True
        svc.update(performance_sampling_interval=10.0)
        assert svc.get().performance.sampling_interval == 10.0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_settings_performance_validation_rejects_out_of_range():
    tmp = tempfile.mkdtemp()
    try:
        svc = SettingsService(JobStore(Path(tmp) / "db.db"))
        with pytest.raises(ValueError):
            svc.update(performance_sampling_interval=999.0)
        with pytest.raises(ValueError):
            svc.update(performance_max_samples_per_job=5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Facade via ReelminnerApplication (PART 3.6 integration root)
# --------------------------------------------------------------------------- #
@pytest.fixture
def app():
    tmp = tempfile.mkdtemp()
    ReelminnerApplication._instance = None
    application = ReelminnerApplication.get_instance(data_dir=tmp)
    yield application
    try:
        application.close()
    finally:
        ReelminnerApplication._instance = None
        shutil.rmtree(tmp, ignore_errors=True)


def test_app_performance_capabilities_and_monitoring(app):
    caps = app.performance.get_capabilities()
    assert caps.cpu_logical >= 0
    time.sleep(0.5)  # let the monitor thread take its first sample
    snap = app.performance.get_system_snapshot()
    assert snap is not None
    assert "cpu_percent" in snap


def test_app_worker_recommendation_insufficient_without_jobs(app):
    rec = app.performance.get_worker_recommendation()
    assert rec["basis"] == BASIS_INSUFFICIENT


def test_app_performance_history_empty(app):
    hist = app.performance.get_history(job_id=None, limit=10, offset=0)
    assert "summaries" in hist
    assert hist["total"] == 0


def test_app_records_job_performance_on_end(app):
    # Fake a completed job (no browser required).
    cfg = SimpleNamespace(
        workers=3, delay=1.0, network_mode=NetworkMode.DIRECT, proxy_id=None
    )
    now = time.time()
    job = SimpleNamespace(
        id="jobX", status=JobStatus.COMPLETED,
        started_at=now - 10, completed_at=now, created_at=time.ctime(now),
        total_items=10, processed_items=10, successful_items=9,
        failed_items=1, blocked_items=0, rate_limited_items=0,
        error_summary="", config=cfg,
    )
    app.performance.record_job_end(job)
    perf = app.performance.get_job_performance("jobX")
    assert perf["summary"] is not None
    assert perf["summary"]["processed"] == 10
    assert perf["summary"]["bottleneck_label"] in (
        BOTTLENECK_UNKNOWN, BOTTLENECK_NETWORK_LIMITED
    )
    # No sensitive data in the summary dict.
    blob = str(perf["summary"])
    for forbidden in ("password", "cookie", "secret", "token"):
        assert forbidden not in blob


def test_app_no_sensitive_data_in_samples(app):
    cfg = SimpleNamespace(
        workers=2, delay=1.0, network_mode=NetworkMode.DIRECT, proxy_id="px1"
    )
    now = time.time()
    job = SimpleNamespace(
        id="jobY", status=JobStatus.COMPLETED,
        started_at=now - 5, completed_at=now, created_at=time.ctime(now),
        total_items=5, processed_items=5, successful_items=5,
        failed_items=0, blocked_items=0, rate_limited_items=0,
        error_summary="", config=cfg,
    )
    app.performance.record_job_end(job)
    perf = app.performance.get_job_performance("jobY")
    # proxy_id may appear (it is metadata, not a secret), but never credentials.
    assert "password" not in str(perf)
    assert "username" not in str(perf)


# --------------------------------------------------------------------------- #
# MCP tool entry points (PART 17)
# --------------------------------------------------------------------------- #
def test_mcp_performance_tools_registered():
    import mcp_server

    names = mcp_server.registered_tools()
    for tool in (
        "get_system_capabilities", "get_system_performance",
        "get_job_performance", "get_performance_history",
        "get_worker_recommendation", "get_performance_recommendations",
    ):
        assert tool in names


def test_mcp_performance_tools_smoke(app):
    import mcp_server

    caps = mcp_server.get_system_capabilities()
    assert "cpu_logical" in caps
    perf = mcp_server.get_system_performance()
    assert "system" in perf
    rec = mcp_server.get_worker_recommendation()
    assert "basis" in rec
    hist = mcp_server.get_performance_history(limit=10)
    assert "summaries" in hist
    jp = mcp_server.get_job_performance("nope")
    assert jp["summary"] is None
    recs = mcp_server.get_performance_recommendations()
    assert "recommendations" in recs
