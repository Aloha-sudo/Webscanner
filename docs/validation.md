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


## Active SMB inventory (2026-11-06, local feature branch)

`bash scripts/check.sh` passes: 125 Python tests, API fixture and all frontend fixtures.
Coverage includes null/password authentication, NT and LM:NT hashes, Kerberos AES128/AES256,
KDC/SPN binding without NTLM fallback, share enumeration, empty/denied directories,
reparse-point exclusion, depth/entry limits and safe error reporting. SQLite queue fixtures
cover one-use credentials, redelivery, cancellation before publication, login rejection,
expired credentials and enqueue failure. Existing report import, pagination, Unicode search,
project ZIP transfer, migration idempotency and frontend fixtures also pass.
Synthetic import input: `docs/smb-example.json`.

Full frontend typecheck/build could not run: `tsc` and `vite` are absent locally.
Dependency installation failed with `EAI_AGAIN` for `registry.npmjs.org`.
A loopback bind returned `PermissionError (EPERM)`, so real SMB/Kerberos and browser/deployment
verification remain outstanding. Protocol tests use a fake SMB connection; queue tests use
SQLite with a fake broker/secret store. No live database, containers or external servers
were changed. Migration 11 adds nullable job state when the updated backend is deployed.


## Redis queue dependency regression (2026-11-06)

The rebuilt worker exited with Kombu `VersionMismatch`: installed transport required
redis-py >=6.1.0 while requirements pinned redis-py 5.2.0. Memory-broker enqueue tests
could not detect this because they never initialize the Redis transport.
`requirements.txt` now also pins Kombu 5.4.2, supported by Celery 5.4.0 and compatible
with redis-py 5.2.0. The backend/worker image runs `pip check` and a no-network Redis
transport client check immediately after installation. Regression fixtures exercise
that transport and prove incompatible client versions fail before a broker connection.
Container rebuilding and an actual worker ping must still run on the Docker host.

Compatibility references: [Celery 5.4.0](https://github.com/celery/celery/blob/v5.4.0/requirements/default.txt),
[Kombu 5.4.2 Redis requirements](https://github.com/celery/kombu/blob/v5.4.2/requirements/extras/redis.txt).


## SMB NetExec comparison and browsing (2026-11-06)

Read-only inspection of scan 140 catalogs found the same seven share names as the
user-provided NetExec output on the Windows host; existing credentialed reports
also held 553 files / 111 directories. Twenty-two directories hit the depth limit.
Guest authentication and share enumeration denial on the router were recorded.
The missing write-access check and incorrect interpretation of Impacket's SMB 3.1.1
client signing requirement were confirmed in code.

Updated behavior: shares-only by default; check READ on every share and WRITE by
opening existing disk-share roots with access masks (no file creation or ACL changes).
Use server SecurityMode for signing, and mark ambiguous historical SMB 3.1.1 values
unknown in the UI. TCP 445 discovery is concurrent; authentication remains sequential.
Folder collection is an explicit host action with one-use credential re-entry.
Host browsing displays 50 rows with IP/name/account and access filters; file results
remain paginated per selected share. A synthetic 1000-host fixture verifies paging,
filters, share rights, historical signing uncertainty and file-collection handoff.
The per-launch limit is still 256 IPs; this is not a 1000-host scan performance test.

`bash scripts/check.sh` passes: 133 Python tests plus API/frontend fixtures. Real
post-change SMB access and signing must be checked on the Docker host after deployment;
network sockets, Docker access and full Vite/TypeScript builds remain unavailable here.


## Cross-host shares and live file operations (2026-11-07)

Replaced host-by-host navigation with one share table across hosts/accounts. The
initial filter shows only disk shares with observed READ/WRITE; inaccessible,
unverified and service shares remain available through the all-results filter.
A synthetic 200-host/600-share fixture covers the compact default, show-all,
access/name filtering and direct share opening in a modal. File browsing does not
require a prior spider.

Worker-side operations add live directory listing, bounded download (20 MiB), text,
DOCX and XLSX preview, and effective access tests on files/directories. Tests cover
existing read-only handles, zero-valued handles, path/reparse rejection, size limits,
bounded Office XML/text extraction, safe rendering of HTML as text, download links,
one-time action claims, expired sessions, scan/report/host scoping, revoked-session
failure inspection and exclusion of credentials from public state/broker arguments.
The scan-created browser session is limited to explicit targets and lasts 15 minutes;
its credential is retained in Redis for that TTL, independently of the scanner's
one-use credential key. Downloads are ephemeral attachments, not project evidence.

`bash scripts/check.sh` passes: 144 Python tests, the existing API fixture and all
frontend fixtures. A separate actual Celery import/producer fixture registers scan,
DNS, SMB inventory and file-action tasks and enqueues a scan on a memory broker.
It does not establish Redis/Docker or real SMB connectivity. New live operations still
require testing against the user's SMB servers after worker/backend deployment;
full TypeScript/Vite builds and browser screenshots remain unavailable in this sandbox.


## SMB Commander and reconnect regression (2026-11-07)

The old explorer revoked its session when leaving the tab and used nested document
modals plus duplicate connection controls. It now keeps an expiring capability in tab
sessionStorage and opens a dense list/inline inspector workspace. Scope and original
expiry are preserved; credential fields are explicitly excluded from storage. Manual
password/NTLM reuse stays within reported hosts in one scan; Kerberos host/SPN scope
is preserved. Explicit disconnect and server expiry still invalidate access.

Coverage: cache restore across module/page reload, blocked-storage memory fallback,
no revocation on tab unmount, original lease preservation, cross-host scope enforcement,
StrictMode effect replay without duplicate listing, in-flight preview deduplication,
stale preview isolation, keyboard selection, bounded cached previews and fixed SMB
commands with quoted Unicode names/root containment/prototype-key rejection.
`bash scripts/check.sh`: 146 Python tests plus API/frontend fixtures pass. A local
Chromium launch was attempted but ended with TargetClosedError; this is not an actual
browser-layout or live SMB validation. TypeScript/Vite dependencies remain absent in
this environment, so full build and real UI/network verification remain outstanding.

SMB split browsing: regression fixture checks that the overview remains visible beside one explorer, changing shares creates no tabs, and closing the panel preserves the shared session. Full `scripts/check.sh` passes (146 backend tests and frontend fixtures). Browser/Docker validation and Vite/typecheck require the local runtime/dependencies.

Compact SMB setup: fixture verifies default collapse, expansion and collapse after successful launch; existing progress/cancellation checks remain enabled.

SMB result deletion: 151 backend tests and frontend fixtures pass via `bash scripts/check.sh`. New cases cover selected-only deletion, scan isolation, invalid/duplicate IDs, symlink rejection, rollback on move failure, active-job blocking, job-reference cleanup, confirmation/cancel, busy/error states and closing a deleted open panel. CSS parses successfully. Live Docker/browser and TypeScript/Vite build remain unverified in this environment.

Saved SMB file search: `bash scripts/check.sh` passes (155 backend tests and frontend fixtures). Added cases cover wildcard/Unicode/literal characters, scan isolation, latest-per-account selection, merged source evidence, pagination, share-only coverage, truncation, direct exact-file opening before/after connection and stale-response protection. CSS syntax passes. TypeScript/Vite dependencies are absent; no live browser/Docker validation was performed.

SMB search collection UX: 158 backend tests and frontend fixtures pass. Added reuse tests for password/NTLM/Kerberos sessions, scope/revocation/expiry protection and absence of secrets in public jobs/queue arguments. Frontend fixtures cover no-session setup and connected collection without password re-entry. Read-only inspection of local scan 141 showed share-only coverage with zero saved file entries; no live SMB collection was launched. CSS parses; browser/Docker validation remains unavailable.

SMB workbench redesign: full `bash scripts/check.sh` passes (159 backend tests plus frontend fixtures); targeted form/search fixtures also pass after final focus/tooltip adjustments. Regressions cover central connection without duplicate login fields, valid connection defaults when scan options are absent, active-session access rechecks without spider, detected-host pagination, preserved search return, folder/page/filter/selection/scroll restoration, source identity labels and existing deletion/download/preview behavior. CSS syntax and whitespace checks pass. TypeScript/Vite dependencies and a live browser/container connection are unavailable; no new screenshot or live SMB verification is claimed. Existing synthetic gallery scenes are retained with SMB capture guidance.

Secret-search first version: full `bash scripts/check.sh` passes with 175 Python tests (174 passed, 1 explicitly skipped) and frontend fixtures. The skipped test requires the real pinned snaffler-ng package, unavailable because terminal PyPI DNS resolution fails. Tests use injected classification and SMB mocks for redaction, byte/file bounds, candidate selection, queue ID-only payloads, claim-once delivery, cancellation/child termination, expiry/scope checks, explicit queue errors, archive exclusion/import rejection, UI launch/history/live preview/confirmed deletion. CSS syntax and Python/TSX syntax checks pass. Dockerfile adds a real engine contract check for the eventual build. Actual engine accuracy/encoding, package installation, Docker build, browser rendering, TypeScript/Vite build and live SMB scans remain unverified. No user-network secret scan was launched.

Standalone/key-hunting correction: full `scripts/check.sh` passes with 178 backend tests, no skips, and all frontend fixtures. The actual installed snaffler-ng 1.5.13 now passes private-key-header and SSH/PuTTY-name regressions, including key names positioned after 500 other files while the read budget is exhausted. Added project-free context creation and same-page preparation/credential flow, finding substring/wildcard filtering and skip-reason counters. Read-only inspection of local scan 141 showed two id_rsa findings already persisted and a 500-of-558 candidate cutoff in its older run. No old results were rewritten and no live user-network scan was launched. Frontend build dependencies are unavailable; Docker compose inspection cannot read the local .env, so browser/container validation is still outstanding.

The native secret-search workflow additionally exercises snaffler-ng 1.5.13's full
runner on fictional local files in fast and normal modes. Tests cover redaction
before SQLite persistence, searching beyond the first 100 findings, native queue
failure cleanup, host/session isolation for preview, cancellation and stdin-only
credentials. The new compact UI has component fixtures; no new browser screenshot
or TypeScript/Vite build has been validated in this environment.

Multi-source secret-search fixtures additionally run the real native FTP pipeline
with a fake FTP transport and the real local pipeline on temporary files. They
cover FTPS configuration/certificate verification, URL credential rejection,
endpoint/folder scope, read-only local paths and symlink rejection, generic file
worker dispatch, preview/download limits and source-specific request bodies.
No live FTP/FTPS server, Docker rebuild or browser screenshot was tested here.

Advanced secret-search tests cover native depth-zero traversal and directory
exclusions, thread/file-size configuration, aggregate-byte budgets under concurrent
reads, continued filename findings after read exhaustion, partial status, API size
validation, form defaults/reset and runtime-to-seconds conversion.

Secret preview regressions cover missing-session messaging, automatic preview after
reconnection, inline access-denied errors, empty text, historical SMB findings and
text .ppk/.pub key previews. Browser verification of responsive positioning remains
unavailable in this environment; legacy preview grid rules are scoped to their container.
