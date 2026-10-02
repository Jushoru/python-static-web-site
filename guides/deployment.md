# Публикация и проверка сайта

Инструкция для сопровождения проекта.

## Настройка репозитория и первый запуск

1. Открыть репозиторий → **Settings → Pages**.
2. В **Build and deployment → Source** выбрать **GitHub Actions**.
   Дополнительный шаблон Jekyll не требуется: используется workflow проекта.
3. Локально выполнить `python -m nox -s check build`.
4. Добавить исходные файлы в коммит, включая `.github/workflows/pages.yml`,
   `noxfile.py`, зависимости, `data`, `scripts`, `tests` и `docs`. Не добавлять
   `venv`, `.nox`, `.cache`, `_build` и `site`.
5. Выполнить push в `main`.
6. На вкладке **Actions** открыть **Build and deploy report**. Проверить,
   что задания `build` и `deploy` завершились успешно.
7. Открыть URL из результата `deploy` или страницы **Settings → Pages**.

Ожидаемый адрес для этого репозитория:
[GitHub Pages](https://jushoru.github.io/python-static-web-site/).
До первого успешного развёртывания он может возвращать 404.

Для Pages вручную создавать токен или добавлять пароль не требуется:
используются временный `GITHUB_TOKEN` и механизм OIDC GitHub Actions.

## Первое размещение на Helios через SFTP

1. После push обновлённого workflow открыть успешный запуск Actions.
2. Внизу страницы запуска, в **Artifacts**, скачать `helios-site` и распаковать ZIP.
   Найти каталог, в котором непосредственно лежат `index.html`, `assets` и `search`.
3. Через уже настроенное SFTP-подключение открыть
   `/home/studs/s370419/public_html/` и создать внутри папку
   `python-static-web-site`.
4. Загрузить **содержимое** распакованной сборки в эту папку. Не загружать ZIP
   целиком и не создавать лишний вложенный каталог `site-helios`.
5. Убедиться, что итоговый путь главной страницы:
   `/home/studs/s370419/public_html/python-static-web-site/index.html`.
6. Открыть [отчёт на Helios](https://se.ifmo.ru/~s370419/python-static-web-site/)
   и выполнить проверки ниже. До загрузки эта ссылка может возвращать 404.

На сервер передаются готовые HTML, стили, изображения, поисковый индекс и
скачиваемые материалы. Устанавливать Python, Nox и зависимости на Helios
не требуется. Корневые файлы портфолио в `public_html` не заменяются.

Локальная альтернатива скачиванию артефакта:

```powershell
python -m nox -s build -- --config-file mkdocs.helios.yml
```

Результат находится в `site-helios`. Артефакт Actions удобнее для сдачи: он
соответствует конкретному опубликованному коммиту, а локальная сборка может
включать ещё не сохранённые изменения.

Первое размещение через SFTP выполнено вручную. Для дальнейших обновлений
используется задание `deploy-helios`. [Порядок настройки автопубликации](helios-ci.md).

## Проверки после публикации

В PowerShell, после успешного `deploy`:

```powershell
$reportUrl = 'https://jushoru.github.io/python-static-web-site/'
$reportResponse = Invoke-WebRequest -Uri $reportUrl -UseBasicParsing
$reportResponse.StatusCode
$reportResponse.Content.Contains('PYTHON-STATIC-REPORT-T1-P3')

$reportCommit = (git rev-parse HEAD).Trim()
$resultsResponse = Invoke-WebRequest -Uri ($reportUrl + 'results.html') -UseBasicParsing
$resultsResponse.Content.Contains($reportCommit)

$searchResponse = Invoke-WebRequest -Uri ($reportUrl + 'search/search_index.json') -UseBasicParsing
$searchResponse.StatusCode
($searchResponse.Content | ConvertFrom-Json).docs.Count
```

Ожидается: `200`, `True`, `True`, `200` и положительное число записей индекса.
Проверка коммита предполагает, что локальный HEAD — именно опубликованный
коммит. Если после push уже создан следующий локальный коммит, сравнивать
нужно с SHA соответствующего запуска Actions.

HTTP 200 у поискового индекса проверяет его доступность, но не работу интерфейса.
Отдельно открыть сайт, ввести в поиск «кэширование» и перейти к найденной странице.
Проверить переходы между разделами, загрузку графиков и скачивание примера
Markdown с корректным русским текстом.

Те же команды применимы к Helios после замены начального значения:

```powershell
$reportUrl = 'https://se.ifmo.ru/~s370419/python-static-web-site/'
```

На Helios особенно важно проверить переход с главной на внутреннюю страницу,
обе диаграммы и поиск. Также проверить, что прежнее портфолио по адресу
`https://se.ifmo.ru/~s370419/` продолжает открываться.

Для проверки повторного использования кэша на странице успешного запуска
Actions выбрать **Re-run all jobs**. В шаге сборки проверить `Report cache HIT`.
Для подтверждения обновления контента можно изменить обычный абзац на главной,
сделать коммит и push: текст должен обновиться при сохранении `HIT`.
Это проверяет автопубликацию текста. Демонстрация изменения графика требует
отдельного нового набора реальных измерений; подменять числа ради скриншота не нужно.

