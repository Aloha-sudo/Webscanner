# Обновление GitHub

Репозиторий проекта: https://github.com/Aloha-sudo/Webscanner.

Подготовленный комплект находится в `github-release/prepared/`:

- `webscanner-source.zip` — все исходники без рабочей базы, сканов, `.env`, локальных превью, зависимостей и Git-истории.
- `webscanner-update.zip` — только файлы, изменившиеся относительно указанного в `files-manifest.json` коммита.
- `files-manifest.json` — состав, контрольные суммы и список изменений.
- `SHA256SUMS` — SHA-256 двух ZIP-архивов.
- `UPLOAD.txt` — короткая инструкция для загрузки.

## Через сайт GitHub

Распакуйте **webscanner-update.zip**, откройте репозиторий, выберите **Add file → Upload files** и перетащите распакованные файлы и папки, сохраняя их структуру. Не загружайте сам ZIP вместо исходников. Перед коммитом проверьте список изменений.

Название коммита: `Add direct UDP scanning and simplify scan setup`.

## Через Git

В существующем клоне репозитория сначала синхронизируйте свою ветку и убедитесь, что незакоммиченные изменения сохранены. Наложите содержимое архива обновления на корень клона, затем:

```sh
git status --short
git diff --check
git diff --stat
git add -- README.md README.ru.md CHANGELOG.md .gitignore backend frontend cli docs scripts webscanner
git diff --cached --stat
git commit -m "Add direct UDP scanning and simplify scan setup"
git push origin main
```

Не выполняйте `git add .` из рабочей установки с реальными данными. Не копируйте её локальный `docker-compose.yml` поверх публичного: в комплекте сохранён Compose с настройкой пароля через `.env` и публикацией UI только на localhost. Образец `.env.example` включён; настоящий `.env` исключён.

Архивы предназначены для обновления исходников GitHub. Обновление работающего сервера выполняйте отдельно с резервной копией PostgreSQL и `scans/`, сохраняя прежние учётные данные и имя Compose-проекта. Лицензия исходного кода приложения в этом обновлении не назначается.
