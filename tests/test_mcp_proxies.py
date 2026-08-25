"""MCP tool-layer tests for proxy management (no credentials leak)."""

import json
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


def test_add_proxy_no_credentials_in_response(app):
    out = mcp_server.add_proxy(
        scheme="http", host="1.2.3.4", port=8080,
        username="alice", password="supersecret",
    )
    serialized = json.dumps(out)
    assert "supersecret" not in serialized
    assert "alice" not in serialized
    assert out["has_credentials"] is True
    assert out["status"] == "unknown"


def test_import_proxies_via_mcp(app):
    res = mcp_server.import_proxies([
        {"raw": "127.0.0.1:8080"},
        {"raw": "http://10.0.0.9:3128"},
    ])
    assert res["added_count"] == 2
    assert mcp_server.list_proxies()["count"] == 2


def test_get_and_update_proxy(app):
    p = mcp_server.add_proxy(scheme="http", host="1.2.3.4", port=8080)
    fetched = mcp_server.get_proxy(p["id"])
    assert fetched["id"] == p["id"]
    updated = mcp_server.update_proxy(p["id"], name="renamed")
    assert updated["name"] == "renamed"


def test_enable_disable_delete_proxy(app):
    p = mcp_server.add_proxy(scheme="http", host="1.2.3.4", port=8080)
    assert mcp_server.disable_proxy(p["id"])["enabled"] is False
    assert mcp_server.enable_proxy(p["id"])["enabled"] is True
    res = mcp_server.delete_proxy(p["id"])
    assert res["deleted"] is True
    assert mcp_server.get_proxy(p["id"]) is None


def test_test_proxy_runs_health_check(app):
    p = mcp_server.add_proxy(scheme="http", host="1.2.3.4", port=8080)
    status = mcp_server.test_proxy(p["id"])
    assert "status" in status
    assert "username" not in status and "password" not in status


def test_proxy_list_response_has_no_credentials(app):
    mcp_server.add_proxy(scheme="http", host="1.2.3.4", port=8080,
                         username="bob", password="hidden")
    out = mcp_server.list_proxies()
    serialized = json.dumps(out)
    assert "hidden" not in serialized
    assert "bob" not in serialized
