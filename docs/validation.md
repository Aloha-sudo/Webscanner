# Repository validation

Checked on 2026-11-02. The repository root is now the single working source tree; see [the Git workflow](github.md). Runtime databases, real scan reports and screenshots, credentials, backups, local previews, dependency folders and Git history are excluded. The documentation gallery and demo project contain the existing synthetic examples.

Checks run for this update:

- 104 Python unit tests on SQLite and mocked services: passed.
- API fixture: enqueue/retry, malformed import metadata, custom UDP ports, rejected removed proxy requests and queue failures passed.
- All frontend JavaScript logic and component fixtures in `frontend/tests/run.cjs`: passed.
- TS/TSX and CSS syntax parsing: passed.
- Documentation links, source/update archive contents, checksums and common credential patterns: checked during packaging.
- Shared Compose uses `.env` password configuration and defaults to localhost binding. The ignored local dotenv and override preserve the existing Kali project, container names, database volume, network and port binding. Both configurations were validated without starting services.

The package preserves the published frontend test/typecheck commands and their declared Babel dependencies. Local deployment settings are excluded by `.gitignore`; archived source packages are not used for further development. Existing source licensing is unchanged.

Not verified in this environment:

- A full Vite build and TypeScript typecheck: frontend packages are not installed, and package-registry access is unavailable.
- Docker image builds and full PostgreSQL/Redis/Celery startup: Docker engine access is unavailable.
- Live network scanning and browser integration: the environment blocks the required sockets.
- Dependency lockfiles are not supplied, so builds are not fully reproducible.

The gallery captures predate the compact protocol/UDP form changes; they are retained as documentation of the broader interface, not as verification of the updated layout.
