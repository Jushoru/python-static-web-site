"""Render the static T1 decision model; these are judgments, not benchmark data.

Run manually after editing data/ssg_comparison.json. Outputs are committed with
the report; ordinary MkDocs builds do not rerun this editorial calculation.
"""

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]


def render():
    source = ROOT / "data" / "ssg_comparison.json"
    model = json.loads(source.read_text(encoding="utf-8"))
    tools, rows, groups = model["tools"], model["criteria"], model["groups"]
    if len(tools) != 4 or len(rows) != 18 or len({r["id"] for r in rows}) != 18:
        raise ValueError("Expected four tools and 18 unique criteria")
    if sum(groups.values()) != 100 or any(r["group"] not in groups for r in rows):
        raise ValueError("Invalid groups")
    for group, weight in groups.items():
        if sum(r["weight"] for r in rows if r["group"] == group) != weight:
            raise ValueError(f"Weights do not add up for {group}")
    for row in rows:
        if row["weight"] < 0 or len(row["scores"]) != len(tools):
            raise ValueError(f"Invalid criterion: {row['id']}")
        if row["weight"] == 0:
            if any(s is not None for s in row["scores"]):
                raise ValueError("Unmeasured criterion must use null scores")
        elif any(type(s) is not int or s not in range(4) for s in row["scores"]):
            raise ValueError("Scores must be integers from zero to three")

    contributions = {
        group: [sum(r["weight"] * r["scores"][i] / 30 for r in rows
                    if r["group"] == group and r["weight"]) for i in range(4)]
        for group in groups
    }
    totals = [sum(values[i] for values in contributions.values()) for i in range(4)]
    order = sorted(range(4), key=lambda i: totals[i], reverse=True)
    assets = ROOT / "docs" / "assets" / "theory"
    assets.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "svg.hashsalt": "ssg-theory-v1"})
    fig, ax = plt.subplots(figsize=(10, 5.3), layout="constrained")
    left = [0.0] * 4
    for (group, values), color in zip(contributions.items(), ["#2864a5", "#258679", "#cb8824"]):
        widths = [values[i] for i in order]
        ax.barh(range(4), widths, left=left, height=0.58, color=color,
                label=f"{group} ({groups[group]}%)")
        left = [a + b for a, b in zip(left, widths)]
    ax.set_yticks(range(4), [tools[i] for i in order])
    ax.invert_yaxis()
    ax.set_xlim(0, 10)
    ax.set_xticks(range(11))
    ax.set_xlabel("Взвешенная оценка, от 0 до 10")
    ax.set_title("SSG для публикации результатов экспериментов\n"
                 "Экспертная модель; производительность не оценивалась", pad=16)
    for y, i in enumerate(order):
        ax.text(totals[i] + 0.08, y, f"{totals[i]:.2f}", va="center", fontweight="bold")
    ax.set_axisbelow(True)
    ax.xaxis.grid(True, alpha=0.2)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=1, frameon=False)
    fig.savefig(assets / "ssg-comparison.svg", metadata={"Date": None})
    fig.savefig(assets / "ssg-comparison.png", dpi=160)
    plt.close(fig)
    (assets / "ssg-comparison.json").write_bytes(source.read_bytes())

    lines = [
        "# T1: оценки и диаграмма", "",
        "Это **авторская модель выбора**, а не результаты тестирования четырёх программ. "
        "[Возможности, источники и ограничения](theory.md) объясняют оценки. "
        "Дата проверки документации: " + model["review_date"] + ".", "",
        "## Шкала и веса", "",
        "| Балл | Смысл |", "| --- | --- |",
        "| 3 | Развитая поддержка критерия в выбранном основном стеке; обычная настройка |",
        "| 2 | Поддержка с ограничениями или через отдельное документированное расширение |",
        "| 1 | Частичное решение, ручная работа или собственная интеграция |",
        "| 0 | В рассматриваемой конфигурации решения нет |",
        "| — | Нет сопоставимых измерений; критерий исключён из суммы |", "",
        "Оценка относится ко всему критерию: например, показ формулы ещё не означает "
        "наличия сквозной нумерации и ссылок на уравнения. Баллы 3 не означают, что "
        "каждая возможная подфункция встроена в ядро. Выбор расширений указан в сравнении.", "",
        "**Научный контент — 65%.** Наибольшие веса у формул и воспроизводимых вычислений "
        "(по 12%); затем библиография (9%), рисунки и таблицы (по 8%). "
        "Это приоритеты исследовательского отчёта, а не блога или справочника API.", "",
        "**Вёрстка и вывод — 20%.** Половина веса блока приходится на выпуск HTML и "
        "печатной версии из одного источника. **Эксплуатация — 15%.** "
        "Для небольшого отчёта сопровождение важно, но не доминирует над содержанием.", "",
        "## Матрица", "",
        "| Критерий | Вес, % | MkDocs + Material | Sphinx + MyST | Pelican | Quarto |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        scores = " | ".join("—" if s is None else str(s) for s in row["scores"])
        lines.append(f"| [{row['name']}](theory.md#{row['id']}) | {row['weight']} | {scores} |")
    lines += ["", "Сумма весов: **100%**. Вес производительности равен нулю из-за "
              "отсутствия общего эксперимента. Это ограничивает итоговый рейтинг.", "",
              "## Расчёт", "",
              "Для каждого инструмента: `итог = сумма(вес × балл) / 30`. "
              "Делитель 30 переводит максимум `100 × 3 = 300` в шкалу 0–10. "
              "Например, 12% и 2 балла за формулы дают `12 × 2 / 30 = 0,8` итогового балла.", "",
              "| Инструмент | Научный контент (макс. 6,5) | Вёрстка (макс. 2) | Эксплуатация (макс. 1,5) | Итог / 10 |",
              "| --- | ---: | ---: | ---: | ---: |"]
    for i in order:
        values = " | ".join(f"{v[i]:.2f}" for v in contributions.values())
        lines.append(f"| {tools[i]} | {values} | **{totals[i]:.2f}** |")
    lines += ["", "Расчёт ведётся без промежуточного округления. Два знака после запятой "
              "показывают арифметику, а не точность экспертного мнения.", "",
              "![Вклад трёх групп критериев в итоговую оценку каждого SSG](assets/theory/ssg-comparison.svg)", "",
              "Каждый цвет — вклад группы с учётом её веса. Длина всей полосы совпадает "
              "с итогом таблицы. Диаграмма статическая и не загружает JavaScript с CDN.", "",
              "## Файлы и воспроизводимость расчёта", "",
              "[Исходные веса и баллы (JSON)](assets/theory/ssg-comparison.json), "
              "[диаграмма SVG](assets/theory/ssg-comparison.svg), "
              "[диаграмма PNG](assets/theory/ssg-comparison.png).", "",
              "| Файл диаграммы | Размер, байт | Размер, КиБ (1024 байта) |",
              "| --- | ---: | ---: |"]
    for suffix in ("svg", "png"):
        size = (assets / f"ssg-comparison.{suffix}").stat().st_size
        lines.append(f"| {suffix.upper()} | {size} | {size / 1024:.2f} |")
    lines += ["", "Веса и баллы хранятся в `data/ssg_comparison.json`. После их изменения "
              "нужно выполнить в активированном окружении:", "", "```powershell",
              "python scripts/render_theory.py", "python -m nox -s build", "```", "",
              "Первый шаг проверяет сумму весов и диапазон баллов, заново создаёт эту "
              "страницу и обе диаграммы. Полученные файлы сохраняются в Git. "
              "Обычная сборка сайта использует их как статические материалы. "
              "Эксперимент P3 и его кэш работают отдельно.", "",
              "## Как читать результат", "",
              "В выбранном сценарии лидирует **Quarto**: исполнение вычислений, научная "
              "разметка и несколько форматов вывода составляют большую долю оценки. "
              "**Sphinx** близок по научным возможностям и особенно удобен для справочника API. "
              "Разница не доказывает универсального превосходства: веса и баллы субъективны.", "",
              "Изменение одного балла по критерию с весом 12% меняет итог на 0,4. "
              "Поэтому небольшое отличие итогов следует обсуждать вместе с требованиями, "
              "а не считать статистически значимым. "
              "[Условия смены выбора и объяснение использования MkDocs](theory.md#conclusion).", ""]
    (ROOT / "docs" / "theory-scores.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(zip(tools, totals)), ensure_ascii=True))


if __name__ == "__main__":
    render()
