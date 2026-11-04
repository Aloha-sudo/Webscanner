# WebScanner workspace

- This repository root is the single working source tree. Make code changes here, not in release folders or extracted archives.
- Keep `.env`, `docker-compose.override.yml`, `.local/`, `scans/` and `backups/` local. Preserve running installation data, Compose project identity and database credentials.
- `docker-compose.yml` is the shared publishable configuration. Machine-specific container names and settings belong in ignored overrides and `.env`.
- Run `bash scripts/check.sh` for Python unit tests, the API fixture, frontend fixtures and whitespace checks. Use `npm run typecheck` and `npm run build` in `frontend/` when its dependencies are installed.
- Update the RU/EN UI strings and relevant documentation for user-visible changes. Maintain both README languages and the existing synthetic gallery.
- Use normal Git diffs, commits and pushes from this root. Release archives are optional historical artifacts, not another source of truth.
- Source files and `.git` should be owned by the normal developer account. If root-owned files prevent user commits, `scripts/fix_workspace_owner.sh` can be run once on the host; it excludes runtime data and dependencies. Root-run tools can use a per-command `git -c safe.directory=/home/kali/codex-AD/webscanner ...` override if needed; do not edit global Git configuration.
