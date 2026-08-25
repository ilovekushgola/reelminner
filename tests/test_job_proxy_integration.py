"""Tests for Job + Proxy integration (network_mode / FIXED_PROXY)."""

import threading

import pytest

from app import ReelminnerApplication
from job_manager import JobManager
from proxies import ProxyManager, ProxyStore, ProxySecretStore, NetworkMode


@pytest.fixture
def app(tmp_path):
    application = ReelminnerApplication(data_dir=tmp_path, db_name="reelminner.db")
    # Ensure the singleton used by code paths points at this temp instance.
    ReelminnerApplication._instance = application
    yield application
    ReelminnerApplication._instance = None
    application.close()


def _add_proxy(app, host="10.0.0.5", port=3128):
    return app.proxies.add_proxy(scheme="http", host=host, port=port)["id"]


def test_create_job_defaults_to_direct(app):
    job = app.jobs.create_job(urls=["https://instagram.com/reel/abc"])
    assert job.config.network_mode == NetworkMode.DIRECT
    assert job.config.proxy_id is None
    d = app.jobs  # noqa
    assert job.config.network_mode.value == "direct"


def test_create_job_fixed_proxy_stores_proxy_id(app):
    pid = _add_proxy(app)
    job = app.jobs.create_job(
        urls=["https://instagram.com/reel/abc"],
        network_mode=NetworkMode.FIXED_PROXY,
        proxy_id=pid,
    )
    assert job.config.network_mode == NetworkMode.FIXED_PROXY
    assert job.config.proxy_id == pid
    # Persisted and round-trips through the store.
    reloaded = app.jobs.get_job(job.id)
    assert reloaded.config.proxy_id == pid
    assert reloaded.config.network_mode == NetworkMode.FIXED_PROXY


def test_proxy_id_cleared_when_direct(app):
    pid = _add_proxy(app)
    job = app.jobs.create_job(
        urls=["https://instagram.com/reel/abc"],
        network_mode=NetworkMode.DIRECT,
        proxy_id=pid,  # must be ignored for DIRECT
    )
    assert job.config.proxy_id is None


def test_resolver_called_for_fixed_proxy(app):
    pid = _add_proxy(app)
    job = app.jobs.create_job(
        urls=["https://instagram.com/reel/abc"],
        network_mode=NetworkMode.FIXED_PROXY,
        proxy_id=pid,
    )
    proxy_dict = app.jobs._resolve_proxy(job)
    assert proxy_dict is not None
    assert proxy_dict["server"] == "http://10.0.0.5:3128"
    # The application wires the proxy manager as the default resolver.
    assert app.jobs._proxy_resolver is not None


def test_missing_proxy_falls_back_to_direct(app):
    # proxy_id points at a proxy that does not exist.
    job = app.jobs.create_job(
        urls=["https://instagram.com/reel/abc"],
        network_mode=NetworkMode.FIXED_PROXY,
        proxy_id="proxy_does_not_exist",
    )
    proxy_dict = app.jobs._resolve_proxy(job)
    assert proxy_dict is None
    # And no proxy usage is recorded (run.proxy_id would be None in start path).
    assert job.config.proxy_id == "proxy_does_not_exist"


def test_disabled_proxy_falls_back_to_direct(app):
    pid = _add_proxy(app)
    app.proxies.disable_proxy(pid)
    job = app.jobs.create_job(
        urls=["https://instagram.com/reel/abc"],
        network_mode=NetworkMode.FIXED_PROXY,
        proxy_id=pid,
    )
    assert app.jobs._resolve_proxy(job) is None


def test_existing_jobs_without_proxy_still_work(app):
    # A job created without any proxy selection must remain DIRECT and valid.
    job = app.jobs.create_job(urls=["https://instagram.com/reel/abc"])
    assert job.config.network_mode == NetworkMode.DIRECT
    assert app.jobs._resolve_proxy(job) is None


def test_proxy_usage_recorded_on_finish(app):
    pid = _add_proxy(app)
    # The application wires job_manager.on_proxy_used -> app._on_proxy_used.
    assert app.jobs._on_proxy_used is not None
    # Simulate the finally-block behaviour from _run for a completed job.
    app.jobs._on_proxy_used(pid, True, "")
    # Success recorded in proxy metadata via the wired callback.
    meta = app.proxies.get_proxy(pid)
    assert meta["success_count"] == 1
    assert meta["last_used_at"] is not None
