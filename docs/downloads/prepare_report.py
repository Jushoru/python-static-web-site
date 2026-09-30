"""Validate benchmark data and generate report pages and a local static chart."""

import csv
import hashlib
import io
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

from benchmark import CONFIG, FIELDS, SECTION


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
DATA = ROOT / "data" / "build_times.csv"
METADATA = DATA.with_suffix(".metadata.json")


def write_if_changed(path, content):
    """Avoid triggering a new live-reload build when generated content is identical."""
    payload = content.encode("utf-8") if isinstance(content, str) else content
    if path.exists() and path.read_bytes() == payload:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def read_measurements(data_path=DATA, metadata_path=METADATA):
    metadata = json.loads(metadata_path.read_text(encoding="utf-8-sig"))
    rows, seen = [], set()
    with data_path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != FIELDS:
            raise ValueError(f"Unexpected CSV columns: {reader.fieldnames}")
        for number, raw in enumerate(reader, 2):
            try:
                row = {
                    "dataset_version": raw["dataset_version"],
                    "pages": int(raw["pages"]),
                    "repeat": int(raw["repeat"]),
                    "build_seconds": float(raw["build_seconds"]),
                    "site_bytes": int(raw["site_bytes"]),
                }
                if not math.isfinite(row["build_seconds"]) or row["build_seconds"] <= 0:
                    raise ValueError("Build time must be finite and positive")
                if min(row["pages"], row["repeat"], row["site_bytes"]) <= 0:
                    raise ValueError("Counts and size must be positive")
                if row["dataset_version"] != metadata["dataset_version"]:
                    raise ValueError("Dataset version differs from metadata")
                key = row["pages"], row["repeat"]
                if key in seen:
                    raise ValueError("Duplicate page count and repeat")
                seen.add(key)
            except (ValueError, TypeError, KeyError) as error:
                raise ValueError(f"Invalid CSV row {number}: {error}") from error
            rows.append(row)
    expected = {
        (pages, repeat)
        for pages in metadata["pages"]
        for repeat in range(1, metadata["repeats"] + 1)
    }
    if not rows or seen != expected:
        raise ValueError("CSV measurements are incomplete or differ from metadata")
    return sorted(rows, key=lambda row: (row["pages"], row["repeat"])), metadata


def summarize(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["pages"]].append(row)
    result = []
    for pages, samples in sorted(groups.items()):
        times = [row["build_seconds"] for row in samples]
        sizes = [row["site_bytes"] for row in samples]
        result.append({
            "pages": pages, "count": len(times), "times": times,
            "mean": statistics.mean(times), "median": statistics.median(times),
            "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
            "minimum": min(times), "maximum": max(times),
            "mean_bytes": statistics.mean(sizes),
        })
    return result


def make_chart(summary):
    # A static chart keeps published results usable without external CDNs.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "svg.hashsalt": "mkdocs-benchmark"})
    fig, (timing, size) = plt.subplots(1, 2, figsize=(11, 4.5), layout="constrained")
    pages = [item["pages"] for item in summary]
    for item in summary:
        timing.scatter([item["pages"]] * item["count"], item["times"], color="#94a3b8", s=24, zorder=2)
    timing.errorbar(pages, [item["mean"] for item in summary],
                    yerr=[item["stdev"] for item in summary], fmt="o", color="#2563eb",
                    capsize=6, markersize=7, label="Среднее ± выборочное СКО", zorder=3)
    timing.scatter([], [], color="#94a3b8", s=24, label="Отдельные измерения")
    timing.set(title="Время полной сборки", xlabel="Число страниц", ylabel="Время, с")
    timing.legend(loc="upper left", fontsize=9)
    values = [item["mean_bytes"] / 2**20 for item in summary]
    bars = size.bar([str(p) for p in pages], values, color="#0f766e", width=0.5)
    size.bar_label(bars, fmt="%.2f", padding=5)
    size.set(title="Размер готового сайта", xlabel="Число страниц", ylabel="Средний размер, МиБ")
    size.set_ylim(0, max(values) * 1.18)
    timing.set_xticks(pages)
    upper = max(max(item["times"] + [item["mean"] + item["stdev"]]) for item in summary)
    timing.set_ylim(bottom=0, top=upper * 1.2)
    for axis in (timing, size):
        axis.grid(axis="y", alpha=0.2)
        axis.set_axisbelow(True)
        axis.spines[["top", "right"]].set_visible(False)
    for extension in ("svg", "png"):
        buffer = io.BytesIO()
        metadata = {"Date": None} if extension == "svg" else {}
        fig.savefig(buffer, format=extension, dpi=160, metadata=metadata)
        write_if_changed(DOCS / "assets" / "generated" / f"build-times.{extension}", buffer.getvalue())
    plt.close(fig)


def number(value, places=3):
    return f"{value:.{places}f}".replace(".", ",")


def table_cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def results_page(rows, metadata, summary):
    lines = [
        "# Результаты эксперимента", "",
        "Эта страница, таблицы и график автоматически сформированы из исходного CSV.",
        "При исправлении данных результаты обновляются во время следующей сборки отчёта.", "",
        f"**Версия данных:** {table_cell(metadata['dataset_version'])}. **Количество измерений:** {len(rows)}.", "",
        "[Методика и работа скрипта](practice.md) · [Пример тестовой страницы](example.md)", "",
        "## График", "",
        "![Среднее время сборки с разбросом и размер готового сайта](assets/generated/build-times.svg)", "",
        "Серые точки — отдельные измерения. Синие точки — средние значения; вертикальные",
        "отрезки показывают плюс-минус одно выборочное стандартное отклонение (СКО).",
        "Это характеристика разброса повторов, а не доверительный интервал среднего.",
        "Для единственного повтора СКО оценить нельзя; на графике отрезок не отображается.", "",
        "График сохранён локально и не требует внешних CDN. "
        "[Скачать SVG](assets/generated/build-times.svg) · [Скачать PNG](assets/generated/build-times.png)", "",
        "## Сводная таблица", "",
        "| Страниц | Повторов | Среднее, с | Медиана, с | СКО, с | Минимум, с | Максимум, с | Средний размер, МиБ |",
        "| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary:
        stdev = number(item["stdev"]) if item["count"] > 1 else "—"
        lines.append(f"| {item['pages']} | {item['count']} | {number(item['mean'])} | {number(item['median'])} | {stdev} | {number(item['minimum'])} | {number(item['maximum'])} | {number(item['mean_bytes'] / 2**20, 2)} |")
    lines += ["", "Размер включает все файлы тестового сайта: HTML, стили, JavaScript, поисковый индекс",
              "и другие ресурсы. 1 МиБ = 1 048 576 байт. Это не размер одной страницы и не объём",
              "сетевой передачи с HTTP-сжатием.", "", "## Интерпретация", ""]
    if len(summary) > 1:
        first, last = summary[0], summary[-1]
        lines.append(f"При увеличении объёма с {first['pages']} до {last['pages']} страниц среднее время "
                     f"изменилось с {number(first['mean'])} до {number(last['mean'])} с "
                     f"(отношение: {number(last['mean'] / first['mean'], 2)}).")
    lines += ["Эти результаты относятся к указанному компьютеру и тестовым страницам. По небольшому",
              "числу размеров и повторов нельзя установить универсальный закон роста времени",
              "или сделать вывод, что MkDocs быстрее другого генератора.", "",
              "## Все исходные измерения", "",
              "| Страниц | Повтор | Время, с | Размер сайта, байт |", "| ---: | ---: | ---: | ---: |"]
    for row in rows:
        lines.append(f"| {row['pages']} | {row['repeat']} | {number(row['build_seconds'], 6)} | {row['site_bytes']} |")
    lines += ["", "## Среда измерений", "", "| Параметр | Значение |", "| --- | --- |"]
    environment = {
        "Начало эксперимента, UTC": metadata["started_at_utc"],
        "Операционная система": f"{metadata['system']} {metadata['system_release']}",
        "Процессор (идентификатор системы)": metadata["processor"],
        "Логических процессоров": metadata["logical_cpu_count"],
        "Python": metadata["python"], "MkDocs": metadata["packages"]["mkdocs"],
        "Material": metadata["packages"]["mkdocs-material"],
        "Прогревочных сборок на размер": metadata["warmups_per_size"],
        "Начальное значение перемешивания": metadata["order_seed"],
    }
    lines += [f"| {label} | {table_cell(value)} |" for label, value in environment.items()]
    lines += ["", "## Скачать исходные материалы", "",
              "- [Измерения CSV](downloads/build_times.csv)",
              "- [Параметры эксперимента JSON](downloads/build_times.metadata.json)",
              "- [Пакеты среды измерений](downloads/benchmark_environment.txt)",
              "- [Скрипт эксперимента](downloads/benchmark.py)",
              "- [Скрипт обработки](downloads/prepare_report.py)", "",
              "Список пакетов среды измерений сохранён отдельно от зависимостей отчёта: "
              "Matplotlib установлен позднее для обработки уже полученных данных.", "",
              "CSV проверяется на положительные конечные значения времени, дубликаты повторов,",
              "полноту измерений и соответствие версии и параметров файлу JSON. Некорректные",
              "данные останавливают сборку, чтобы не публиковать вводящий в заблуждение график.", ""]
    return "\n".join(lines)


def example_page():
    # Same expressions as create_fixture(), without changing the measured script.
    sample = "# Страница 1\n\n" + "".join(SECTION.format(section=i) for i in range(1, 9))
    intro = """# Пример тестовой страницы

Ниже показано полное содержимое первой страницы, которую создаёт эксперимент:
заголовок и восемь разделов. Оно формируется из того же шаблона `SECTION` в
`scripts/benchmark.py`, поэтому текст не переписан вручную для демонстрации.

Остальные тестовые страницы отличаются номером в заголовке. Главная записывается
в `index.md`, вторая — в `page-0001.md` и так далее. Число страниц в команде
включает главную: при `--pages 10` создаются ровно десять Markdown-файлов.

**Таблицы и код внутри примера — фиксированный тестовый материал.** Числа 100 и 5
в этих таблицах не являются результатами измерений и не меняют параметры скрипта.
Код Python показывается с подсветкой; MkDocs не выполняет его при сборке.

[Скачать точный Markdown примера](downloads/example-page.md.txt) ·
[Посмотреть реальные результаты](results.md) · [Вернуться к методике](practice.md)

Скачиваемый текстовый файл сохранён в UTF-8 с меткой BOM, чтобы браузер правильно
определял кодировку русского текста даже без указания кодировки сервером.

Содержимое совпадает с тестовой страницей, но здесь оно показано внутри навигации
отчёта. У временных сайтов свой заголовок `Benchmark` и меню из 10, 50 или 100 страниц.

---

"""
    write_if_changed(DOCS / "example.md", intro + sample)
    # MkDocs' development server sends text/plain without a charset. A UTF-8 BOM
    # makes the downloadable Russian source unambiguous to browsers and editors.
    write_if_changed(DOCS / "downloads" / "example-page.md.txt", sample.encode("utf-8-sig"))
    write_if_changed(DOCS / "downloads" / "benchmark-config.yml", CONFIG)


def main():
    rows, metadata = read_measurements()
    snapshot = ROOT / "data" / "benchmark_environment.txt"
    if hashlib.sha256(snapshot.read_bytes()).hexdigest() != metadata["requirements_sha256"]:
        raise ValueError("Benchmark environment snapshot does not match recorded checksum")
    summary = summarize(rows)
    make_chart(summary)
    example_page()
    write_if_changed(DOCS / "results.md", results_page(rows, metadata, summary))
    for source in (DATA, METADATA, snapshot, ROOT / "scripts" / "benchmark.py", Path(__file__)):
        write_if_changed(DOCS / "downloads" / source.name, source.read_bytes())
    print(f"Report prepared: {len(rows)} measurements, {len(summary)} page counts.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError) as error:
        print(f"Cannot prepare report: {error}", file=sys.stderr)
        sys.exit(1)
