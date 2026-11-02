# Validation of the GitHub source update

Prepared on 2026-11-02 from the current working source. Runtime databases, real scan reports and screenshots, credentials, backups, local previews, dependency folders and Git history are excluded. The documentation gallery and demo project contain the existing synthetic examples.

Checks run for this update:

- 104 Python unit tests on SQLite and mocked services: passed.
- API fixture: enqueue/retry, malformed import metadata, custom UDP ports, rejected removed proxy requests and queue failures passed.
- All frontend JavaScript logic and component fixtures in `frontend/tests/run.cjs`: passed.
- TS/TSX and CSS syntax parsing: passed.
- Documentation links, source/update archive contents, checksums and common credential patterns: checked during packaging.
- Published Compose configuration is retained from the existing repository: `.env` password configuration and UI bound to localhost. It is validated with a placeholder password; no services are started.

The package preserves the published frontend test/typecheck commands and their declared Babel dependencies. Local deployment-specific Compose settings are not copied into the public source folder. Existing source licensing is unchanged.

Not verified in this environment:

- A full Vite build and TypeScript typecheck: frontend packages are not installed, and package-registry access is unavailable.
- Docker image builds and full PostgreSQL/Redis/Celery startup: Docker engine access is unavailable.
- Live network scanning and browser integration: the environment blocks the required sockets.
- Dependency lockfiles are not supplied, so builds are not fully reproducible.

The gallery captures predate the compact protocol/UDP form changes; they are retained as documentation of the broader interface, not as verification of the updated layout.
