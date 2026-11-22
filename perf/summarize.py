"""Turn a Locust run's CSV files into the rows for docs/testing/performance-reliability.md.

    python perf/summarize.py perf/results/load-20261124-1830 --profile load --commit abc1234

The argument is the --csv prefix given to Locust (it writes <prefix>_stats.csv and
<prefix>_stats_history.csv). Prints a row for the staging results table, a
per-endpoint p95 table, and whether the run meets NFR-2 (p95 <= 2000 ms for every
endpoint and error rate < 1%). Numbers are copied as Locust measured them.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path

P95_LIMIT_MS = 2000
ERROR_LIMIT = 0.01


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def _num(value: str) -> float:
    return float(value) if value not in ("", "N/A") else 0.0


def summarize(prefix: str, profile: str, commit: str) -> str:
    stats = _rows(Path(f"{prefix}_stats.csv"))
    history_path = Path(f"{prefix}_stats_history.csv")
    history = _rows(history_path) if history_path.exists() else []

    total = next(r for r in stats if r["Name"] == "Aggregated")
    endpoints = [r for r in stats if r["Name"] != "Aggregated"]

    requests = int(total["Request Count"])
    failures = int(total["Failure Count"])
    error_rate = failures / requests if requests else 0.0
    peak_rps = max((_num(r["Requests/s"]) for r in history if r["Name"] == "Aggregated"), default=_num(total["Requests/s"]))
    worst_p95 = max((_num(r["95%"]) for r in endpoints), default=_num(total["95%"]))
    meets = worst_p95 <= P95_LIMIT_MS and error_rate < ERROR_LIMIT
    when = datetime.fromtimestamp(Path(f"{prefix}_stats.csv").stat().st_mtime).strftime("%d %b %Y %H:%M")

    lines = [
        "Staging results row:",
        "",
        f"| {when} | `{commit}` | {profile} | {requests} | {_num(total['Average Response Time']):.0f} "
        f"| {_num(total['95%']):.0f} | {_num(total['Max Response Time']):.0f} | {error_rate:.2%} "
        f"| {peak_rps:.1f} | {'Yes' if meets else 'No'} |",
        "",
        "Per-endpoint p95:",
        "",
        "| Endpoint | Requests | Failures | Avg (ms) | p95 (ms) | Max (ms) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for r in sorted(endpoints, key=lambda r: _num(r["95%"]), reverse=True):
        lines.append(
            f"| {r['Name']} | {r['Request Count']} | {r['Failure Count']} | {_num(r['Average Response Time']):.0f} "
            f"| {_num(r['95%']):.0f} | {_num(r['Max Response Time']):.0f} |"
        )
    lines += [
        "",
        f"NFR-2: worst endpoint p95 = {worst_p95:.0f} ms (limit {P95_LIMIT_MS}), "
        f"error rate = {error_rate:.2%} (limit {ERROR_LIMIT:.0%}) -> {'meets' if meets else 'does not meet'} NFR-2",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prefix", help="the --csv prefix used for the Locust run")
    parser.add_argument("--profile", required=True, choices=["smoke", "load", "progressive", "spike"])
    parser.add_argument("--commit", required=True, help="commit deployed on staging during the run")
    args = parser.parse_args()
    print(summarize(args.prefix, args.profile, args.commit))


if __name__ == "__main__":
    main()
