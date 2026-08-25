"""Tests for the Phase 3.5 proxy management layer (proxies.py)."""

import json

import pytest

from app_events import ApplicationEventBus, AppEventKind
from proxies import (
    ProxyManager,
    ProxyStore,
    ProxySecretStore,
    ProxyStatus,
    NetworkMode,
    DuplicateProxyError,
    ProxyNotFoundError,
    parse_proxy_input,
)


@pytest.fixture
def pm(tmp_path):
    db = tmp_path / "reelminner.db"
    secrets = tmp_path / "proxy_secrets.json"
    store = ProxyStore(db)
    sec = ProxySecretStore(secrets)
    bus = ApplicationEventBus()
    manager = ProxyManager(
        store,
        sec,
        event_bus=bus,
        health_url="http://127.0.0.1:9/probe",
        health_timeout=0.5,
    )
    return {"mgr": manager, "store": store, "sec": sec, "bus": bus}


def test_parse_proxy_input_bare_host_port():
    comp = parse_proxy_input("127.0.0.1:8080")
    assert comp == {"scheme": "http", "host": "127.0.0.1", "port": 8080}


def test_parse_proxy_input_with_scheme():
    comp = parse_proxy_input("socks5://10.0.0.1:1080")
    assert comp["scheme"] == "socks5"
    assert comp["port"] == 1080


def test_parse_proxy_input_with_auth():
    comp = parse_proxy_input("http://user:secretpass@1.2.3.4:3128")
    assert comp["username"] == "user"
    assert comp["password"] == "secretpass"
    assert comp["scheme"] == "http"


def test_parse_proxy_input_invalid():
    with pytest.raises(ValueError):
        parse_proxy_input("not-a-proxy")


def test_add_proxy_sanitizes_output(pm):
    safe = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080,
                               username="alice", password="s3cret")
    assert "username" not in safe
    assert "password" not in safe
    assert safe["scheme"] == "http"
    assert safe["host"] == "1.1.1.1"
    assert safe["has_credentials"] is True
    assert safe["status"] == ProxyStatus.UNKNOWN.value


def test_credentials_stored_separately(pm):
    pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080,
                        username="alice", password="s3cret")
    raw = pm["sec"]._path.read_text(encoding="utf-8")
    blob = json.loads(raw)
    # Exactly one proxy secret, credentials present in the SEPARATE file only.
    assert len(blob) == 1
    creds = next(iter(blob.values()))
    assert creds["username"] == "alice"
    assert creds["password"] == "s3cret"


def test_add_duplicate_skip(pm):
    first = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080)
    second = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080,
                                 username="bob", password="x")
    assert first["id"] == second["id"]


def test_add_duplicate_error(pm):
    pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080)
    with pytest.raises(DuplicateProxyError):
        pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080,
                            on_duplicate="error")


def test_import_proxies(pm):
    res = pm["mgr"].import_proxies([
        {"raw": "127.0.0.1:8080"},
        {"raw": "http://10.0.0.1:3128"},
        {"scheme": "http", "host": "10.0.0.2", "port": 3129},
        {"raw": "bad"},
    ])
    assert res["added_count"] == 3
    assert res["error_count"] == 1
    assert len(pm["mgr"].list_proxies()) == 3


def test_get_update_delete(pm):
    p = pm["mgr"].add_proxy(name="p1", scheme="http", host="1.1.1.1", port=8080)
    got = pm["mgr"].get_proxy(p["id"])
    assert got["name"] == "p1"
    updated = pm["mgr"].update_proxy(p["id"], name="p1-renamed")
    assert updated["name"] == "p1-renamed"
    pm["mgr"].delete_proxy(p["id"])
    assert pm["mgr"].get_proxy(p["id"]) is None
    with pytest.raises(ProxyNotFoundError):
        pm["mgr"].delete_proxy(p["id"])


def test_enable_disable(pm):
    p = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080)
    disabled = pm["mgr"].disable_proxy(p["id"])
    assert disabled["status"] == ProxyStatus.DISABLED.value
    assert disabled["enabled"] is False
    enabled = pm["mgr"].enable_proxy(p["id"])
    assert enabled["enabled"] is True
    assert enabled["status"] != ProxyStatus.DISABLED.value


def test_build_scrape_proxy_none_when_disabled(pm):
    p = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080,
                            username="u", password="p")
    pm["mgr"].disable_proxy(p["id"])
    assert pm["mgr"].build_scrape_proxy(p["id"]) is None
    pm["mgr"].enable_proxy(p["id"])
    d = pm["mgr"].build_scrape_proxy(p["id"])
    assert d is not None
    assert d["server"] == "http://1.1.1.1:8080"
    assert d["username"] == "u"
    assert d["password"] == "p"


def test_test_proxy_records_health(pm):
    p = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080)
    result = pm["mgr"].test_proxy(p["id"])
    # Probe URL is unreachable -> UNHEALTHY, failure counted, no creds leaked.
    assert result["status"] in (ProxyStatus.UNHEALTHY.value, ProxyStatus.ERROR.value)
    assert result["failure_count"] >= 1
    assert "username" not in result
    assert "password" not in result


def test_usage_tracking(pm):
    p = pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080)
    pm["mgr"].record_usage(p["id"])
    pm["mgr"].record_success(p["id"])
    pm["mgr"].record_failure(p["id"], "connect timeout")
    got = pm["mgr"].get_proxy(p["id"])
    assert got["success_count"] == 1
    assert got["failure_count"] == 1
    assert got["last_used_at"] is not None
    assert got["error_summary"] == "connect timeout"


def test_events_never_contain_credentials(pm):
    captured = []
    pm["bus"].subscribe(lambda e: captured.append((e.kind, e.payload)))
    pm["mgr"].add_proxy(scheme="http", host="1.1.1.1", port=8080,
                        username="alice", password="TOPSECRET")
    pm["mgr"].update_proxy(pm["mgr"].list_proxies()[0]["id"],
                          username="alice2", password="TOPSECRET2")
    serialized = json.dumps([payload for _kind, payload in captured])
    assert "TOPSECRET" not in serialized
    assert "TOPSECRET2" not in serialized
    kinds = [kind for kind, _ in captured]
    assert AppEventKind.PROXY_CREATED in kinds
    assert AppEventKind.PROXY_UPDATED in kinds
