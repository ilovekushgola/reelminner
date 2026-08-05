import run_qa
from scraper import ReelData


def make_rows():
    ok = ReelData(username="u", reel_url="https://www.instagram.com/reel/A/",
                  music_title="t", music_artist="a", likes="10",
                  comments="1", caption="c", uploaded_at="2026-01-01")
    orig = ReelData(username="v", reel_url="https://www.instagram.com/reel/B/",
                    music_title="Original audio", is_original_audio=True)
    fail = ReelData(username="", reel_url="https://www.instagram.com/reel/C/",
                    status="session_expired")
    return [ok, ok, orig, fail]


def test_compute_metrics_basics():
    m = run_qa.compute_metrics(make_rows(), runtime_s=42.0)
    assert m["total"] == 4
    assert m["ok_count"] == 3
    assert m["original_audio_count"] == 1
    assert m["status_counts"] == {"ok": 3, "session_expired": 1}
    assert m["runtime_s"] == 42.0


def test_music_fill_excludes_original_audio():
    m = run_qa.compute_metrics(make_rows(), runtime_s=1.0)
    # 2 licensed ok rows, both with music -> 1.0
    assert m["fill"]["music_title"] == 1.0


def test_username_fill_only_counts_ok_rows():
    m = run_qa.compute_metrics(make_rows(), runtime_s=1.0)
    # 3 ok rows, all have username -> 1.0 (the session_expired row is excluded)
    assert m["fill"]["username"] == 1.0


def test_gates_pass_for_good_data():
    rows = [r for r in make_rows() if r.status == "ok"]
    m = run_qa.compute_metrics(rows, runtime_s=100.0)
    passed = {name for name, ok in run_qa.evaluate_gates(m) if ok}
    assert passed == {g["name"] for g in run_qa.GATES}


def test_gates_fail_on_poor_data():
    rows = [
        ReelData(status="session_expired"),
        ReelData(status="timeout"),
        ReelData(status="unavailable"),
    ]
    m = run_qa.compute_metrics(rows, runtime_s=5.0)
    assert run_qa.evaluate_gates(m) != [g for g in run_qa.GATES]
    # explicitly: ok_rate, username fill, music fill, session gates fail
    failed = {name for name, ok in run_qa.evaluate_gates(m) if not ok}
    assert "ok_rate >= 0.75" in failed
    assert "no session_expired" in failed
