#!/bin/sh
# Run on the deployment host where Docker access is available.
set -eu
cd "$(dirname "$0")/.."
active=$(docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "$1"' sh "SELECT count(*) FROM scans WHERE lower(status::text) IN ('queued','running') OR dns_status IN ('queued','running')")
if [ "$active" != '0' ]; then
  echo 'Дождитесь завершения сканов и DNS-задач перед резервным копированием.' >&2
  exit 1
fi
backup_dir="backups/full-before-project-transfer-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
trap 'rm -f "$backup_dir/postgres.dump.partial" "$backup_dir/workspace.tar.gz.partial"' EXIT HUP INT TERM
docker compose exec -T postgres sh -c 'exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup_dir/postgres.dump.partial"
test -s "$backup_dir/postgres.dump.partial"
docker compose exec -T postgres pg_restore --list < "$backup_dir/postgres.dump.partial" > "$backup_dir/postgres-contents.txt"
mv "$backup_dir/postgres.dump.partial" "$backup_dir/postgres.dump"
tar --exclude='./backups' --exclude='./.git' --exclude='./.agents' --exclude='./.aws' --exclude='./.codex' -czf "$backup_dir/workspace.tar.gz.partial" .
tar -tzf "$backup_dir/workspace.tar.gz.partial" > /dev/null
mv "$backup_dir/workspace.tar.gz.partial" "$backup_dir/workspace.tar.gz"
(cd "$backup_dir" && sha256sum postgres.dump workspace.tar.gz > SHA256SUMS)
echo "Резервная копия базы и файлов: $backup_dir"
