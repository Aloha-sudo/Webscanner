# Validation of the GitHub source package

The source package is prepared separately from the working installation. No runtime database, reports, screenshots, private backups or existing Git history are included.

Checks run against this prepared folder:

- 88 Python unit tests on SQLite / mocked services: passed.
- API retry fixture: passed.
- `npm test`: all JavaScript logic and component fixtures passed, including RU / EN and 24-hour time.
- TS / TSX and CSS syntax parsing: passed.
- Local documentation links and package contents: passed.
- Compose interpolation/configuration validation: passed using a placeholder password; no services were started.

Limits of this environment:

- A complete Vite build and TypeScript type check require frontend packages that were not installed in the preparation environment.
- Docker engine access is unavailable here; image builds and a full PostgreSQL / Redis / Celery startup have not been verified for this package.
- Scanner execution against a real target and browser integration were not run.
- Dependency lockfiles are not supplied; resolve and review dependencies in your own environment before treating a build as reproducible.

The package includes declared Babel test dependencies and `npm test` so these checks do not depend on globally installed development packages on a new machine.
