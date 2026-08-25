"""End-to-end QA harness for the Instagram reel scraper.

Runs the real engine over a URL corpus with the user's saved session,
measures data-quality gates, writes qa_report.json + qa_results.csv, and
exits 0 iff every gate passes.

Usage:
  python run_qa.py                    # full run over tests/corpus.txt
  python run_qa.py --quick            # 1 URL, headless, no delay (iteration)
  python run_qa.py --url <reel-url>   # single custom URL (repeatable)
  python run_qa.py --report-only      # show the last report without running
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from scraper import Reelminner, write_csv

PROJECT = Path(__file__).resolve().parent
CORPUS = PROJECT / "tests" / "corpus.txt"
QA_DIR = PROJECT / "results" / "qa"
REPORT_JSON = QA_DIR / "qa_report.json"
REPORT_CSV = QA_DIR / "qa_results.csv"

GATES = [
    {"name": "engine completed (crash-free)", "fn": lambda m: True},
    {"name": "ok_rate >= 0.75", "fn": lambda m: (m["ok_count"] / max(m["total"], 1)) >= 0.75},
    {"name": "username fill >= 0.80", "fn": lambda m: m["fill"]["username"] >= 0.80},
    {"name": "music fill >= 0.60 (licensed only)", "fn": lambda m: m["fill"]["music_title"] >= 0.60},
    {"name": "no session_expired", "fn": lambda m: m["status_counts"].get("session_expired", 0) == 0},
    {"name": "runtime <= 1800s", "fn": lambda m: m["runtime_s"] <= 1800},
]

FILL_FIELDS = ("username", "music_title", "music_artist", "likes", "comments", "caption", "uploaded_at")


def compute_metrics(results, runtime_s: float) -> dict:
    total = len(results)
    status_counts: dict = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1
    ok_rows = [r for r in results if r.status == "ok"]
    licensed = [r for r in ok_rows if not r.is_original_audio]

    def fill(rows, attr: str) -> float:
        if not rows:
            return 0.0
        return round(
            sum(1 for r in rows if (getattr(r, attr) or "").strip()) / len(rows), 3
        )

    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "runtime_s": round(runtime_s, 1),
        "total": total,
        "ok_count": len(ok_rows),
        "original_audio_count": sum(1 for r in ok_rows if r.is_original_audio),
        "status_counts": status_counts,
        "fill": {f: fill(licensed if f.startswith("music") else ok_rows, f) for f in FILL_FIELDS},
        "failures": [
            {"url": r.reel_url, "status": r.status, "music": r.music_title}
            for r in results
            if r.status != "ok"
        ],
    }


def evaluate_gates(metrics: dict) -> list:
    return [(g["name"], g["fn"](metrics)) for g in GATES]


def print_report(metrics: dict, gates: list | None = None) -> None:
    gates = gates or evaluate_gates(metrics)
    print("\n================ QA REPORT ================")
    print(f"timestamp     : {metrics['timestamp']}")
    print(f"runtime       : {metrics['runtime_s']}s")
    print(f"total         : {metrics['total']}")
    print(f"ok            : {metrics['ok_count']}")
    print(f"original audio: {metrics['original_audio_count']}")
    print(f"status counts : {metrics['status_counts']}")
    print("\n-- field fill rates (ok rows; music = licensed only) --")
    for f, v in metrics["fill"].items():
        print(f"  {f:<14}: {v}")
    print("\n-- failures --")
    for fr in metrics["failures"]:
        print(f"  [{fr['status']}] {fr['url']}  music={fr['music']!r}")
    print("\n-- gates --")
    all_ok = True
    for name, passed in gates:
        all_ok = all_ok and passed
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print(f"\nRESULT: {'ALL GATES PASS' if all_ok else 'GATES FAILED'}")
    print(f"report: {REPORT_JSON}")
    print(f"csv   : {REPORT_CSV}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", default=str(CORPUS))
    ap.add_argument("--url", action="append", default=[], help="extra reel URL (repeatable)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--delay", type=float, default=2.0)
    ap.add_argument("--quick", action="store_true", help="1 URL, headless, no delay")
    ap.add_argument("--headless", action="store_true", help="run browsers invisible")
    ap.add_argument("--report-only", action="store_true", help="print last report, no run")
    args = ap.parse_args()

    if args.report_only:
        if REPORT_JSON.exists():
            print_report(json.loads(REPORT_JSON.read_text(encoding="utf-8")))
        else:
            print("[!] no report yet - run the harness first")
        return 0

    urls: list = []
    if Path(args.corpus).exists():
        urls += [
            l.strip()
            for l in Path(args.corpus).read_text(encoding="utf-8").splitlines()
            if l.strip()
        ]
    urls += args.url
    if not urls:
        print("[x] no URLs found (corpus missing?)")
        return 1

    headless = args.headless or args.quick
    workers = 1 if args.quick else args.workers
    delay = 0.0 if args.quick else args.delay
    if args.quick:
        urls = urls[:1]

    scraper = Reelminner(headless=headless, workers=workers, delay=delay)
    if not scraper.has_session():
        print("[x] FAIL: no valid session. Re-import cookies (storage_state.json).")
        return 1

    QA_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[>] QA run: {len(urls)} URL(s), workers={workers}, "
          f"headless={headless}, delay={delay}s")
    t0 = time.time()
    results = scraper.scrape(urls)
    runtime_s = time.time() - t0

    metrics = compute_metrics(results, runtime_s)
    REPORT_JSON.write_text(
        json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_csv(results, REPORT_CSV)

    gates = evaluate_gates(metrics)
    print_report(metrics, gates)
    return 0 if all(p for _, p in gates) else 1


if __name__ == "__main__":
    sys.exit(main())
