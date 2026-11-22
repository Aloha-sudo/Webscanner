# Поиск секретов / Secret search

## Один запуск

1. Откройте «Поиск секретов».
2. Выберите источник: **SMB**, **FTP / FTPS** или **Локальная папка**. Для SMB введите IP/подсеть и учётку; для FTP — URL и способ входа; для локальной папки — путь внутри `secret-inputs`.
3. Нажмите **«Начать поиск»**. Движок сам обнаружит доступные шары, обойдёт файлы и
   покажет находки. Проект, портовый скан, подготовка каталогов в SMB и выбор шар
   вручную не нужны.
4. Фильтруйте общую таблицу по имени, пути или правилу: `id_rsa`, `*.ppk`, `passwd`.
   Фильтр проверяет **весь результат**, страницы по 100 строк не ограничивают поиск.
5. Нажмите файл: справа появится просмотр. Здесь же можно скачать файл. Значения
   секретов в результатах скрыты; просмотр заново читает файл под текущей учёткой.

Поддерживаются анонимный вход, пароль, NT/LM:NT и Kerberos AES с явными KDC/SPN.
Пароль виден при вводе, после запуска поле очищается; в хранилище браузера только
временный токен. Для повторного запуска другой учёткой есть кнопка на этой же странице.
Для просмотра старых результатов истёкшее подключение можно восстановить здесь же,
без повторного поиска. История свёрнута. Остановка и удаление с подтверждением рядом
с результатом. Удаление не меняет файлы на удалённом сервере.

Переход «Найти секреты» из SMB подставляет адрес и выбранную шару; ограничение можно
снять кнопкой «Все шары». SMB остаётся самостоятельным файловым менеджером.

## Как читать находки

Список оформлен компактными строками: иконка и имя файла, папка и размер; отдельно
хост/шара, понятная категория, тип совпадения (имя или содержимое) и приоритет проверки.
Цвет дополняется текстом. Исходное правило остаётся видимым, длинные пути не растягивают
таблицу: полностью они доступны по наведению и в панели просмотра справа. Приоритет
означает порядок ручной проверки, а не доказательство действующего секрета.
При выборе файла строка подсвечивается; её выбор сохраняет подсветку после обновления
списка во время поиска. Заголовки закреплены при прокрутке, фильтр проверяет весь результат.

## Параметры поиска

Под формой есть свёрнутый блок **«Параметры поиска»**. Настройки сохраняются в запуске
и подставляются при повторе; их можно посмотреть рядом с результатом.

| Параметр | По умолчанию | Значение |
|---|---|---|
| Глубина | Без ограничения | `0` — файлы в корне; `1` — ещё один уровень папок; до 100 |
| Время | 30 минут | От 1 минуты до 4 часов |
| Максимальный файл | 10 МиБ | Ограничение движка, до 1024 МиБ |
| Читать из файла | 2 МиБ | Лимит содержимого, до 64 МиБ и не больше максимального файла |
| Общий объём анализа | Без ограничения | До 102400 МиБ прочитанных файлов |
| Максимум чтений файлов | Без ограничения | Число попыток чтения содержимого, до 1000000 |
| Потоки | 60 | Общий пул обнаружения шар/обхода/анализа, от 3 до 60 |
| Только эти шары | Все доступные | SMB-маски, например `C$` или `Docs*`, по одной на строку |
| Исключить шары | `IPC$` | SMB-маски; `IPC$` исключена всегда |
| Исключить папки | Пусто | Маски полного пути, например `*/Temp`, по одной на строку |

Объём считается по прочитанным байтам файлов, не по сетевому трафику или размеру
распакованных данных. После достижения общего объёма/числа чтений проверка следующих
имён продолжается, результат помечается неполным. Счётчики показывают число чтений и МиБ.
Время ограничивает весь запуск; уже найденное сохраняется при остановке/таймауте.

Предел чтения не означает обязательное чтение начала любого большого файла: штатные
правила движка могут оставить его только на классификацию имени. Отключение быстрого
режима убирает его дополнительные исключения, но штатные правила DISCARD остаются.
«Сбросить параметры» возвращает стандартные значения и быстрый режим.

## FTP / FTPS

Выберите «FTP / FTPS», укажите, например, `ftp://192.168.1.126:2121/data`.
Логин и пароль вводятся отдельно от URL; для анонимного входа выберите «Без учётки».
Переключатель FTPS включает явный TLS и проверку сертификата сервера. Это FTP с TLS,
не SFTP/SSH. Несколько адресов можно вводить с новой строки. Имена хостов также допустимы.

Движок обходит указанную папку и подкаталоги. Поиск, просмотр и скачивание используют
тот же адрес, порт и область пути. Никакие команды записи/удаления на FTP не отправляются.
При истёкшем подключении введите FTP-учётку прямо здесь; повторять поиск не нужно.

## Локальные папки

«Локальная» означает папку **на сервере Webscanner**, а не на компьютере, где открыт
браузер. В Docker backend и worker получают одну папку, подключённую только для чтения:

```bash
mkdir -p secret-inputs/client-backup
# Скопируйте свои файлы в secret-inputs/client-backup.
sudo docker compose up -d --build backend worker frontend
```

В интерфейсе выберите «Локальная папка», введите `client-backup` и нажмите «Начать поиск».
Точка `.` означает всю `secret-inputs`; несколько папок — с новой строки. Учётка не нужна.
Можно проверять заранее скачанные документы, выгрузки или каталоги исходного кода.
Это не отдельный движок анализа Git-истории: проверяются находящиеся в папке файлы.
Ссылки на файлы/папки и переходы `..` не используются. Предпросмотр и скачивание остаются
внутри выбранной области. Содержимое не добавляется в сохранённый результат.

Для другой папки на хосте задайте `SECRET_INPUT_DIR=/полный/путь` в локальном `.env`
и пересоздайте backend/worker. В интерфейсе пути по-прежнему относительные этой папке.
`secret-inputs/` исключена из Git. Загрузка файлов через браузер пока не реализована.

## Движок и режимы

Под капотом **полный runner snaffler-ng 1.5.13**, а не собственный обход сохранённого
каталога. Используются его штатные правила имён, содержимого, ключей/сертификатов и
архивов, классификация и параллельный обход. Поддержка конкретного формата определяется
движком и его правилами; универсального чтения любых документов нет.

Быстрый режим соответствует native `--fast`: исключает набор системных каталогов и
ограничивает число потоков обхода одной шары. Снимите галочку для обычного режима.
Каждый запуск имеет новую базу состояния — аналог `--fresh`. `IPC$` исключена всегда.
Проверки записи и копирование найденных файлов на диск отключены. Административные
шары рассматриваются самим движком при наличии доступа.

Ограничения нового запуска: до 256 явно указанных IP, 30 минут по умолчанию;
форма и API допускают 1–240 минут и необязательную глубину. Для FTP разрешено до 256 явно заданных URL; локальные папки ограничены подключённой областью.
Ограничения размера/чтения настраиваются
в форме (по умолчанию файл до 10 МиБ, чтение до 2 МиБ).
Старые лимиты обвязки в 500 чтений, 1000 находок и 50 МиБ **не применяются** к новому
runner. Неответивший первый IP в подсети не прерывает обнаружение остальных хостов.
Ошибка авторизации останавливает новые попытки; найденные значения не используются
для автоматического входа в другие системы.

## Хранение и проверка

В `scans/<id>/secret-jobs/<uuid>/` хранятся `state.json` и `engine.sqlite3` с путями,
правилами, уровнем, счётчиками и `[redacted]`. Match/context редактируются **до записи
в SQLite**; содержимое файлов не сохраняется. Результаты не входят в ZIP проекта.
Учётка хранится временно в Redis: отдельное подключение для задания и 15-минутное
подключение для просмотра. Worker удаляет своё подключение при завершении. Секрет
передаётся child-процессу через stdin, а не argv/логи/файлы. При остановке/таймауте
дочерний процесс завершается, уже полученные находки остаются доступны.

После обновления пересоберите backend, worker и frontend:

```bash
sudo docker compose up -d --build backend worker frontend
```

Docker build проверяет библиотечный API и полный runner на вымышленных локальных
файлах. Локальные тесты сравнивают быстрый/обычный режимы, отсутствие открытых значений
в базе, поиск за первой страницей, область файловых операций и остановку worker.
Реальная пользовательская сеть в этих тестах не сканируется. В текущей среде браузер
не запускается, frontend-зависимости для TypeScript/Vite не установлены; визуальная
проверка новой страницы и сборка контейнеров здесь не подтверждены.

## English

Enter targets and an identity, then press **Start search**. The complete pinned
snaffler-ng runner discovers shares, traverses files and classifies findings in one
background job, without a project or pre-collected SMB catalog. Fast mode uses native
system-folder exclusions; disable it for normal traversal. Each run starts fresh;
IPC$ and write checks are excluded. Default runtime is 30 minutes, up to 256 IPs.

The compact table searches all saved findings, paginates by 100 and opens a preview
only after selecting a file. Credentials can be changed or reconnected on the same
page. Password/NTLM/AES and anonymous modes are supported. History is collapsed;
stop and confirmed deletion are available. SQLite stores redacted classifications,
not matched values or document bytes. Explicit preview/download reads again with
the current scoped identity. Synthetic tests cover both native modes and lifecycle;
real-network and browser/container verification remain separate deployment checks.


Additional sources: choose FTP/FTPS for URL-based traversal with anonymous or
username/password authentication (explicit TLS validates the certificate). Choose
Local folder for files under the read-only `secret-inputs` bind mount shared by
backend and worker. Enter a relative folder or `.`; this is a server directory,
not the browser computer. Set `SECRET_INPUT_DIR` in the local Compose environment
to expose a different host directory. Uploads and SFTP are not implemented.
All sources use the same findings, preview/download, history and stop/delete flow.
Synthetic tests run the real local/FTP pipelines with fictional files and fake FTP
transport; live FTP/FTPS network and browser/container tests remain unverified here.


Advanced settings are collapsed by default and persist with each run: depth
(0 = root files only, blank = unlimited), 1–240 minute runtime, maximum file/read
sizes, optional total analyzed-byte and file-read budgets, 3–60 worker threads,
share include/exclude patterns and directory exclusion globs. Budget exhaustion
preserves filename detection and marks the result partial. Defaults retain native
limits and unlimited aggregate reads. A task-specific Celery timeout and credential
TTL cover the longer runtime. Read bytes measure input file data, not network traffic.

Findings use compact file rows with type icons, prominent filenames, secondary
folder/size, separate host/share and match reason, and text-labelled review priority.
The inspector retains the full path and rule; table headers stay visible while scrolling.
This visual update has component-fixture validation, not a new browser screenshot.

Если подключение истекло, панель просмотра показывает причину и кнопку перехода
к форме подключения. После входа выбранный файл открывается автоматически; старые
SMB-находки с report_id также открываются справа. Ошибки чтения, пустой файл и
неподдерживаемый формат различаются. Текстовые .ppk/.pub доступны для просмотра.
На узких экранах просмотр переходит под список и прокручивается в видимую область.

Expired connections now show an inline reconnect prompt; the selected file reopens
after authentication. Legacy SMB findings use their report reference. Empty files,
read failures and unsupported formats have distinct states. The inspector uses
scoped responsive grid rules and is revealed on narrow screens.
