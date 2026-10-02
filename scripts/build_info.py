"""Fresh build provenance and cache timing tables, rendered without editing docs."""

import csv
import importlib.util
import json
import math
import os
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_cache_spec = importlib.util.spec_from_file_location("report_cache_outputs", ROOT / "scripts/report_cache.py")
_cache_module = importlib.util.module_from_spec(_cache_spec)
_cache_spec.loader.exec_module(_cache_module)


def git_output(*arguments):
    try:
        result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True,
                                text=True, encoding="utf-8", errors="replace", timeout=10)
        return result.stdout.strip() if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def read_build_info(report_status):
    commit = os.environ.get("GITHUB_SHA") or git_output("rev-parse", "HEAD") or "не определён"
    # Derived report files may differ across platforms after generation. They do
    # not represent edits to source data/code. Keep all other changes visible.
    changes = git_output("status", "--porcelain", "--untracked-files=normal", "--", ".",
                         *(f":(exclude)docs/{name}" for name in _cache_module.OUTPUTS))
    metadata = json.loads((ROOT / "data/build_times.metadata.json").read_text(encoding="utf-8-sig"))
    return {
        "commit": commit,
        "worktree": "не определено" if changes is None else ("есть локальные изменения" if changes else "чистое"),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "dataset_version": metadata["dataset_version"],
        **report_status,
    }


def provenance_table(info):
    return "\n".join([
        "| Параметр | Значение |", "| --- | --- |",
        f"| Коммит исходников | `{info['commit']}` |",
        f"| Рабочая папка | {info['worktree']} |",
        f"| Дата сборки | {info['built_at']} |",
        f"| Версия данных | {info['dataset_version']} |",
        f"| Кэш обработки | `{info['status']}` |",
        f"| Ключ кэша | `{info['key']}` |",
    ])


def cache_timings(current_key):
    data = ROOT / "data/cache_timings.csv"
    meta_path = data.with_suffix(".metadata.json")
    if not data.exists() or not meta_path.exists():
        return "Замеры ещё не выполнены. Запустите `python -m nox -s cache-benchmark`, затем пересоберите сайт."
    metadata = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    with data.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    groups = {mode: [] for mode in ("uncached", "cached")}
    seen = set()
    for row in rows:
        mode, repeat, seconds = row["mode"], int(row["repeat"]), float(row["seconds"])
        if mode not in groups or not math.isfinite(seconds) or seconds <= 0 or (mode, repeat) in seen:
            raise ValueError("Invalid cache timing measurement")
        if row["cache_status"] != ("HIT" if mode == "cached" else "BYPASS"):
            raise ValueError("Cache timing status does not match its mode")
        seen.add((mode, repeat))
        groups[mode].append(seconds)
    expected = {(mode, repeat) for mode in groups for repeat in range(1, metadata["repeats"] + 1)}
    if seen != expected or metadata["repeats"] < 2:
        raise ValueError("Incomplete cache timing measurements")
    lines = [f"Дата измерений: {metadata['measured_at_utc']}.", ""]
    if metadata["analysis_key"] != current_key:
        lines += ["!!! warning \"Измерения относятся к другой версии обработки или среде\"",
                  "    Код, данные, зависимости или среда отличаются от замера. Сохранённые цифры —",
                  "    исторический результат; для текущей версии повторите замеры с `-- --force`.", ""]
    lines += ["| Режим | Повторов | Среднее, с | Медиана, с | СКО, с |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for mode, label in (("uncached", "Без кэша"), ("cached", "Из кэша")):
        values = groups[mode]
        lines.append(f"| {label} | {len(values)} | {statistics.mean(values):.4f} | {statistics.median(values):.4f} | {statistics.stdev(values):.4f} |")
    cold, warm = (statistics.mean(groups[mode]) for mode in ("uncached", "cached"))
    lines += ["", "| Показатель | Значение |", "| --- | ---: |",
              f"| Отношение средних времён (без кэша / из кэша) | {cold / warm:.2f} |",
              f"| Сокращение времени, % | {(1 - warm / cold) * 100:.2f} |", "",
              "Ускорение относится только к подготовке результатов. Это не ускорение всего",
              "`nox`, сборки HTML или развёртывания. Во всех запусках байтовое содержимое",
              "сгенерированных результатов проверено на совпадение.", "",
              "### Все измерения кэширования", "",
              "| Режим | Повтор | Время, с | Статус |", "| --- | ---: | ---: | --- |"]
    for row in rows:
        lines.append(f"| {row['mode']} | {row['repeat']} | {float(row['seconds']):.6f} | {row['cache_status']} |")
    runtime = metadata["environment"]
    lines += ["", f"Среда: {runtime['system']}, Python {runtime['python']}, "
              f"Matplotlib {runtime['packages']['matplotlib']}. Полные параметры находятся в `data/cache_timings.metadata.json`."]
    return "\n".join(lines)
