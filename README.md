# WebScanner

A self-hosted workspace for network scans, imported reports and service reachability maps.

**[Документация на русском](README.ru.md)** · [CLI](docs/cli.md) · [Network map](docs/network-map.md) · [Project archives](docs/project-transfer.md) · [RU / EN interface](docs/languages.md)

## Features

- TCP scanning pipeline: **RustScan → Nmap verification → service detection → httpx → Gowitness**.
- Projects and network segments, scan history, retry, cancellation and exclusions.
- Import Nmap, Masscan, RustScan, FastScan, CSV and WebScanner reports.
- Compare host, port, service and web metadata between reports.
- Explore directional service observations from multiple scan sources; export SVG and JSON.
- Resolve hostnames using DNS, including standalone lookup for existing reports.
- Export and import complete project archives with reports, evidence and screenshots.
- Russian and English interface, light/dark themes and a **24-hour clock**.
- Python CLI using the same API.

Maps represent observations in reports, not physical network topology or proof of pivoting access. Missing records do not establish that a host is unreachable or a port is closed.

## Quick start

Requirements: Docker Engine with the Compose plugin. The scanner Dockerfile currently downloads **Linux amd64** tool binaries.

```sh
cp .env.example .env
# Edit .env and set POSTGRES_PASSWORD to your own random, URL-safe value.
# For example, generate one with: openssl rand -hex 24
mkdir -p scans
docker compose up --build -d
```

Open **http://localhost:3000**. Initial image builds install Chromium, RustScan and other tools and can take time.

This distribution binds the web interface to `127.0.0.1`. Change `WEBSCANNER_PORT` in `.env` if port 3000 is already used. There is **no application authentication**: the supplied Compose configuration is intended for local or otherwise controlled access. Scans run from the worker container, not from the browser or CLI machine.

Use the application only for networks you own or are authorized to assess.

## Data and configuration

- PostgreSQL records are stored in the Compose `postgres_data` volume.
- Original reports, tool output and screenshots are stored in `scans/`.
- Redis is the task broker/result backend; backend and worker share the scan directory.
- MinIO is not required by the active local-storage pipeline.
- Language and theme preferences are stored in the browser. Changing language does not change the time zone.

Keep PostgreSQL **and** `scans/` together when backing up. `docker compose down -v` deletes the database volume. For an existing deployment, preserve its Compose project name and database credentials; do not replace them with this example configuration.

An independent `COMPOSE_PROJECT_NAME` is supplied in `.env.example` to avoid accidentally reusing another installation's volume.

## CLI

```sh
./webscanner --help
./webscanner projects list
./webscanner projects create "Example assessment" --part "Lab"
./webscanner scan 192.0.2.10 --project "Example assessment" --part "Lab" --profile quick --wait
```

`192.0.2.10` is a documentation-only example. Replace it with an authorized target reachable from the worker. See [CLI usage](docs/cli.md).

## Development and checks

Python 3.11+ and Node.js 20+:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=backend python3 -m unittest discover -s backend/tests -v
python3 scripts/check_retry_api.py

cd frontend
npm install
npm test
npm run typecheck
npm run build
```

Frontend tests declare their Babel dependencies in `frontend/package.json`. Their runner uses the repository root as the working directory.

The default Vite API proxy targets the Compose service `backend:8000`. For running Vite directly outside Compose, adjust that proxy to your local backend address.

Automated source tests do not replace a full Docker, scanner and browser integration check. See [validation notes](docs/validation.md) for what was verified in this source distribution.

## Repository layout

```text
backend/app/       API, database models, migrations, scan tasks and report adapters
backend/tests/     Python tests
frontend/src/      React / TypeScript interface and translations
frontend/tests/    JavaScript component and logic checks
frontend/public/   Local font assets and their license
cli/               Command-line client
scripts/           API verification and backup helper
docs/             Feature documentation and publication instructions
```

Runtime data, personal backups, scan exports and local credentials are excluded from this repository.

## License

A license for the application source has not been selected yet. See [third-party notices](THIRD_PARTY_NOTICES.md) for bundled fonts and external dependencies.
