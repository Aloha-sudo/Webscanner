#!/usr/bin/env bash
# Run once on the deployment host if development files were created by root.
set -euo pipefail
cd "$(dirname -- "$0")/.."
owner=${1:-${SUDO_USER:-}}
if [[ -z "$owner" || "$owner" == root ]]; then
  echo 'Укажите обычного пользователя: sudo bash scripts/fix_workspace_owner.sh kali' >&2
  exit 1
fi
if [[ $(id -u) != 0 ]]; then
  echo 'Для смены владельца запустите этот скрипт через sudo.' >&2
  exit 1
fi
owner_uid=$(id -u -- "$owner")
owner_gid=$(id -g -- "$owner")
# Do not follow symlinks, enter working data or modify dependency/venv ownership.
find . \( -path './scans' -o -path './backups' -o -path './frontend/node_modules' -o -path './.venv' -o -path './venv' \) -prune \
  -o -exec chown -h -- "$owner_uid:$owner_gid" {} +
printf 'Исходники и .git принадлежат %s. Сканы, backups и окружения не изменялись.\n' "$owner"
