"""MCP tool-layer tests for job + session + results + settings + status."""

import sys
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parent.parent
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

import mcp_server  # noqa: E402
from app import ReelminnerApplication  # noqa: E402


@pytest.fixture
def app(tmp_path):
    application = ReelminnerApplication(data_dir=tmp_path, db_name="reelminner.db")
    ReelminnerApplication._instance = application
    yield application
    ReelminnerApplication._instance = None
    application.close()


def test_create_and_get_job(app):
    job = mcp_server.create_job(urls=["https://instagram.com/reel/abc"])
    assert job["status"] == "created"
    assert job["network_mode"] == "direct"
    fetched = mcp_server.get_job(job["id"])
    assert fetched["id"] == job["id"]


def test_list_jobs(app):
    mcp_server.create_job(urls=["https://instagram.com/reel/abc"])
    out = mcp_server.list_jobs()
    assert out["count"] >= 1
    assert any(j["status"] == "created" for j in out["jobs"])


def test_job_dict_contains_required_fields(app):
    job = mcp_server.create_job(
        urls=["https://instagram.com/reel/abc"],
        network_mode="fixed_proxy",
        proxy_id="proxy_123",
    )
    for key in ("id", "status", "processed", "successful", "failed",
               "blocked", "rate_limited", "session_id", "proxy_id",
               "total_urls", "error_summary"):
        assert key in job
    assert job["network_mode"] == "fixed_proxy"
    assert job["proxy_id"] == "proxy_123"


def test_sessions_list_empty(app):
    out = mcp_server.list_sessions()
    assert out["count"] == 0
    assert out["sessions"] == []


def test_settings_roundtrip(app):
    before = mcp_server.get_settings()
    assert "general" in before
    updated = mcp_server.update_settings({"general": {"default_page_size": 7}})
    assert updated["general"]["default_page_size"] == 7
    reset = mcp_server.reset_settings()
    assert reset["general"]["default_page_size"] != 7


def test_application_status_shape(app):
    mcp_server.create_job(urls=["https://instagram.com/reel/abc"])
    status = mcp_server.get_application_status()
    assert "jobs" in status and "sessions" in status and "proxies" in status
    assert "by_status" in status["jobs"]
    assert status["jobs"]["total"] >= 1
