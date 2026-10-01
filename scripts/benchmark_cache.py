"""Measure actual report preparation with and without its content cache."""

import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from report_cache import OUTPUTS, ROOT, digest, environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "cache_timings.csv")
    parser.add_argument("--force", action="store_true", help="Replace a previous cache timing dataset")
    args = parser.parse_args()
    if args.repeats < 2:
        parser.error("Use at least two repeats per mode")
    metadata_path = args.output.with_suffix(".metadata.json")
    if not args.force and (args.output.exists() or metadata_path.exists()):
        parser.error("Timing results already exist; use --force or another --output")
    stamp = datetime.now(timezone.utc)
    workspace = ROOT / "_build" / "cache-benchmark" / (stamp.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8])
    output_dir, cache_dir = workspace / "docs", workspace / "cache"
    workspace.mkdir(parents=True)
    baseline = None
    key = None

    def run(mode):
        nonlocal baseline, key
        command = [sys.executable, str(ROOT / "scripts" / "prepare_report.py"),
                   "--output-dir", str(output_dir), "--cache-dir", str(cache_dir), "--json"]
        if mode == "uncached":
            command.append("--no-cache")
        started = time.perf_counter()
        completed = subprocess.run(command, cwd=ROOT, capture_output=True, text=True,
                                   encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        elapsed = time.perf_counter() - started
        if completed.returncode:
            raise RuntimeError(completed.stderr or completed.stdout)
        status = json.loads(completed.stdout)
        hashes = {name: digest((output_dir / name).read_bytes()) for name in OUTPUTS}
        if baseline is not None and hashes != baseline:
            raise RuntimeError("Cached and uncached outputs differ")
        if key is not None and key != status["key"]:
            raise RuntimeError("Analysis inputs changed during the benchmark; repeat the run")
        baseline, key = hashes, status["key"]
        return elapsed, status["status"]

    # Font/import/filesystem warm-up, then prime the otherwise empty isolated cache.
    print("Warm-up without cache (excluded from measurements)", flush=True)
    run("uncached")
    print("Priming the report cache (excluded from measurements)", flush=True)
    _, status = run("cached")
    if status != "MISS":
        raise RuntimeError("Expected an empty cache before priming")
    schedule = [(mode, repeat) for repeat in range(1, args.repeats + 1) for mode in ("uncached", "cached")]
    random.Random(42).shuffle(schedule)
    rows = []
    for step, (mode, repeat) in enumerate(schedule, 1):
        elapsed, status = run(mode)
        if status != ("HIT" if mode == "cached" else "BYPASS"):
            raise RuntimeError(f"Unexpected cache status: {status}")
        rows.append({"mode": mode, "repeat": repeat, "seconds": f"{elapsed:.6f}", "cache_status": status})
        print(f"[{step}/{len(schedule)}] {mode}, repeat {repeat}: {elapsed:.3f} s ({status})", flush=True)
    metadata = {
        "measured_at_utc": stamp.isoformat(), "analysis_key": key,
        "repeats": args.repeats, "environment": environment(),
        "order_seed": 42, "execution_order": schedule,
        "timing_scope": "full prepare_report.py subprocess including Python startup; excludes nox setup, package installation, MkDocs HTML build and output verification",
        "warmups": "one uncached run and one cache-priming run; both excluded",
        "outputs_identical": True,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["mode", "repeat", "seconds", "cache_status"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["mode"], row["repeat"])))
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved measured cache timings: {args.output}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Cache benchmark failed: {error}", file=sys.stderr)
        sys.exit(1)
