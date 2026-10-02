# Генераторы статических сайтов для публикации результатов исследований

Учебный отчёт: T1 — сравнение SSG; P3 — воспроизводимый конвейер обработки
измерений времени сборки MkDocs с кэшированием результатов.

- [GitHub Pages](https://jushoru.github.io/python-static-web-site/)
- [Helios](https://se.ifmo.ru/~s370419/python-static-web-site/)
- [Репозиторий](https://github.com/Jushoru/python-static-web-site)

## Локальная сборка

Используется Python 3.14. Из корня проекта в PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip check
python -m virtualenv --version
python -m nox -s check build
python -m nox -s serve
```

Остановка предпросмотра: Ctrl+C. Сборка для Helios:

```powershell
python -m nox -s build -- --config-file mkdocs.helios.yml
```

В Git сохраняются исходные измерения и код. `site/`, `site-helios/`, окружения
и кэш исключены из Git. После push в `main` workflow собирает и публикует отчёт.
Инструкции для сопровождения: [публикация и проверки](guides/deployment.md),
[настройка доступа Helios](guides/helios-ci.md).

## Лицензии

Программный код, примеры кода и конфигурация автоматизации — [MIT](LICENSE).
Текст, данные и иллюстрации проекта — [CC BY 4.0](LICENSE-CONTENT.md),
с оговорками о сторонних материалах, перечисленными в этом файле.
