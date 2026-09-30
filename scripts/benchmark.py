"""Collect real MkDocs build measurements; run separately from report builds."""

import argparse
import csv
import hashlib
import json
import os
import platform
import random
import subprocess
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
CONFIG = """site_name: Benchmark
theme:
  name: material
  language: ru
  font: false
plugins:
  - search:
      lang: [ru, en]
use_directory_urls: false
markdown_extensions:
  - tables
  - pymdownx.superfences
"""
SECTION = """## Раздел {section}

Статический сайт позволяет публиковать результаты эксперимента вместе с описанием
методики. Исходные данные сохраняются отдельно, а таблицы и графики формируются
при обработке. Повторные измерения помогают оценить разброс времени сборки.

| Параметр | Значение |
| --- | --- |
| Число наблюдений | 100 |
| Число повторов | 5 |

```python
values = [1, 2, 3, 4, 5]
mean = sum(values) / len(values)
print(mean)
```

"""
FIELDS = ["dataset_version", "pages", "repeat", "build_seconds", "site_bytes"]


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Value must be a positive integer.")
    return number


def create_fixture(directory, pages):
    docs = directory / "docs"
    docs.mkdir(parents=True)
    (directory / "mkdocs.yml").write_text(CONFIG, encoding="utf-8")
    body = "".join(SECTION.format(section=i) for i in range(1, 9))
    for page in range(pages):
        filename = "index.md" if page == 0 else f"page-{page:04d}.md"
        (docs / filename).write_text(
            f"# Страница {page + 1}\n\n{body}", encoding="utf-8"
        )


def run_build(directory, log_path):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, "-m", "mkdocs", "build", "--clean", "--strict"]
    with log_path.open("w", encoding="utf-8") as log:
        started = time.perf_counter()
        result = subprocess.run(
            command, cwd=directory, env=env, stdout=log, stderr=subprocess.STDOUT
        )
        elapsed = time.perf_counter() - started
    if result.returncode:
        raise RuntimeError(f"Build failed. See log: {log_path}")
    # Counting bytes is deliberately outside the timed part.
    size = sum(p.stat().st_size for p in (directory / "site").rglob("*") if p.is_file())
    return elapsed, size


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pages", nargs="+", type=positive_int, default=[10, 50, 100])
    parser.add_argument("--repeats", type=positive_int, default=5)
    parser.add_argument("--dataset-version", default="v1")
    parser.add_argument("--output", type=Path, default=Path("data/build_times.csv"))
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    if len(set(args.pages)) != len(args.pages):
        parser.error("Page counts must be unique.")
    if not args.dataset_version.strip():
        parser.error("Dataset version must not be empty.")
    output = args.output if args.output.is_absolute() else ROOT / args.output
    metadata_path = output.with_suffix(".metadata.json")
    if output.exists() or metadata_path.exists():
        parser.error("Output already exists. Choose another --output to preserve measurements.")

    packages = {name: version(name) for name in ("mkdocs", "mkdocs-material")}
    started_at = datetime.now(timezone.utc)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    work = ROOT / "_build" / "benchmarks" / run_id
    work.mkdir(parents=True)
    print(f"Logs and temporary sites: {work}", flush=True)
    fixtures = {}
    for pages in args.pages:
        fixture = work / f"pages-{pages}"
        create_fixture(fixture, pages)
        fixtures[pages] = fixture
        print(f"Warm-up: {pages} pages (not included in CSV)", flush=True)
        run_build(fixture, work / f"warmup-{pages}.log")

    # Mix sizes to reduce the effect of a steadily changing background load.
    schedule = [(pages, repeat) for pages in args.pages for repeat in range(1, args.repeats + 1)]
    random.Random(args.seed).shuffle(schedule)
    rows = []
    for step, (pages, repeat) in enumerate(schedule, 1):
        elapsed, size = run_build(fixtures[pages], work / f"pages-{pages}-repeat-{repeat}.log")
        row = dict(zip(FIELDS, [args.dataset_version, pages, repeat, f"{elapsed:.6f}", size]))
        rows.append(row)
        # Keep a recovery copy even if a later measurement fails.
        with (work / "partial_measurements.csv").open("a", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=FIELDS)
            if step == 1:
                writer.writeheader()
            writer.writerow(row)
        print(f"[{step}/{len(schedule)}] {pages} pages, repeat {repeat}: {elapsed:.3f} s; {size} bytes", flush=True)

    metadata = {
        "dataset_version": args.dataset_version,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "system": platform.system(),
        "system_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "logical_cpu_count": os.cpu_count(),
        "packages": packages,
        "pages": args.pages,
        "repeats": args.repeats,
        "warmups_per_size": 1,
        "order_seed": args.seed,
        "execution_order": schedule,
        "sections_per_page": 8,
        "build_command": "python -m mkdocs build --clean --strict",
        "timing_scope": "wall time of subprocess including Python startup and MkDocs cleanup; excludes source generation and byte counting",
        "cache_conditions": "full clean builds after warm-up; operating system file cache is NOT cleared",
        "benchmark_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "requirements_sha256": hashlib.sha256((ROOT / "requirements.txt").read_bytes()).hexdigest(),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda row: (row["pages"], row["repeat"])))
    with metadata_path.open("x", encoding="utf-8") as stream:
        json.dump(metadata, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Saved {len(rows)} measurements: {output}")
    print(f"Experiment metadata: {metadata_path}")


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
