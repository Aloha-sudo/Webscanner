#!/usr/bin/env bash
# Local checks only. Does not start services, commit, push or scan a network.
set -euo pipefail
cd "$(dirname -- "$0")/.."
PYTHONPATH="backend${PYTHONPATH:+:$PYTHONPATH}" python3 -m unittest discover -s backend/tests -q
python3 scripts/check_retry_api.py
npm test --prefix frontend
git -c safe.directory="$(pwd)" diff --check
printf '\nПроверки пройдены. Коммит и push выполняются отдельно.\n'
