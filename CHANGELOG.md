# Changelog

## Unreleased — active SMB inventory

- Fix blank/off-screen secret previews: isolate legacy grid styles, explain expired connections inline, reopen the selected file after reconnecting and support historical SMB findings. Show empty-file and read-error states, support text .ppk/.pub previews and reveal the inspector on narrow screens.

- Improve secret findings with file icons, filename/folder/size hierarchy, separate locations and match categories, theme-aware text priorities, sticky headers and a clearer inspector; keep selected rows highlighted across result refreshes.

- Restore collapsed secret-search tuning: depth, up to four-hour runtime, maximum file/read sizes, aggregate byte/read budgets, threads and share/path exclusions. Persist settings for repeat runs, display consumed bytes and mark budget-limited searches partial without stopping filename classification.

- Add FTP/FTPS and read-only local folders as secret-search sources, with source-specific forms, the full native runner, common findings/preview/download/history and scoped reconnection. Keep local input files ignored by Git and mount the input folder read-only in backend/worker.

- Replace manual secret-search preparation with one native snaffler-ng runner job: fast/normal mode, fresh state, automatic traversal, compact IP/share/file findings, full-result search, scoped preview/download and same-page reconnection. Redact native SQLite findings before persistence; test the real local runner and child lifecycle.

- Give standalone target/credential forms independent theme styles, a compact shared field grid and a single preparation action; remove the ineffective shares-only action in secret mode.

- Make Secret search self-contained: standalone targets without a project/port scan, same-page credential changes and share/file preparation.
- Fix key hunting by classifying metadata before content filtering, keep filename classification beyond 500 reads, and add priority-sorted finding search with wildcard masks and explicit skip reasons. Real pinned-engine regressions cover SSH/PuTTY keys after the first 500 files.

- Add a separate scoped secret-search page and bounded worker jobs using pinned snaffler-ng, with redacted classifications, live file preview, cancellation/history/deletion and an SMB-share entry point. Historical catalog jobs remain readable; new runs use the full native runner. Real-engine local fixtures pass; container/browser verification remains pending.

- Rework SMB into a persistent host/share sidebar and a wide right-hand file/search area, with one central identity form, active-session access rechecks, account-labelled saved results and history/import under ⋯.
- Move preview below the file list and preserve up to 20 share locations, filters, selections and scroll positions; return to the same search results after file viewing.

- Add direct file-list collection beside SMB search using the active scoped password/NTLM/Kerberos session, label the current-folder filter explicitly, and distinguish missing catalogs from no filename matches.

- Display SMB passwords as visible text in inventory and file-connection forms.

- Carry confirmed open TCP 445 hosts into SMB targets with a compact discovered-host list and an explicit setup action; avoid defaulting back to the entire source subnet.

- Preserve file-search path/size columns beside the explorer; scope compact column hiding to the share overview and wrap long paths/accounts.

- Search saved SMB file names/paths across current-scan hosts with wildcard masks, latest-account results, merged source evidence, coverage/partial indicators and direct opening in the right-hand file browser.

- Keep the SMB row-count selector compact on the right beside page navigation (100/200/500/All).

- Delete selected saved SMB catalogs from a compact history table with explicit confirmation, active-job protection and automatic closure of a deleted open result.

- Highlight confirmed SMB share READ/WRITE with green badges and a row marker; keep denied and unknown access neutral.

- Collapse SMB scan setup by default and after launch; keep progress visible and compact the workspace header.

- Open the selected share in a right-hand file panel beside the persistent cross-host overview; click an IP or share name, with no workspace tabs.

- Replace nested SMB dialogs with a Commander-style list/inline-preview workspace, keyboard navigation and fixed optional SMB commands.
- Preserve scoped SMB capabilities across tab/section reloads without storing passwords/hashes/keys; remove automatic disconnect on component unmount.
- Reuse manual password/NTLM connections across reported hosts in the same scan, preserving explicit Kerberos SPN scope.
- Deduplicate preview/StrictMode listing requests and bound session-aware caches for quick navigation.

- Show accessible disk shares across all hosts/accounts in one compact table; hide inaccessible and service shares behind an explicit filter.
- Open shares in a live modal file browser with short-lived, scoped Redis connections; retain the scan connection in browser memory for 15 minutes.
- Add bounded worker-side file download, escaped text/DOCX/XLSX preview and effective file-access checks without modifying remote objects.

- Make share enumeration the default, add non-mutating READ/WRITE access checks, and separate server signing requirements from SMB 3.1.1 client policy.
- Simplify the SMB workflow to targets/authentication, paginated host selection and share access tables; move limits/history to disclosures and collect files on demand.
- Discover TCP 445 concurrently before sequential authentication and report depth limits explicitly.

- Pin Kombu 5.4.2 alongside Celery 5.4.0 and redis-py 5.2.0; validate the Redis transport during image builds to catch incompatible dependencies before deployment.

- Add worker-run SMB inventory with null-session, Windows-password, NTLM hash and Kerberos AES authentication.
- Enumerate shares and directory access; walk real folders and file metadata with progress, limits and cancellation.
- Transfer secrets through expiring single-use Redis keys; keep secrets out of job state, reports, process arguments and Celery payloads.
- Add migration 11 for nullable SMB job state and prevent active inventory deletion/export.
- Keep optional NetExec `spider_plus` JSON import in the scan SMB tab.
- Keep per-import host/account/source/author/check-time provenance, originals and SHA-256.
- Browse shares and inferred folders, search Unicode paths, paginate results and copy UNC paths.
- Preserve SMB attachments through project ZIP export/import.
- Clearly distinguish listed metadata from verified access permissions and file contents.

## 2026-11-02

- Add direct UDP scans using Nmap: common ports, Top 100 UDP and custom port lists.
- Preserve UDP `open|filtered` states during scanning, report import and export, including grouped Nmap results.
- Distinguish uncertain UDP observations from confirmed services in the evidence matrix and network map.
- Keep source, target and protocol controls in a compact row; move UDP details into the profile disclosure.
- Display port states in host cards and send custom UDP ports correctly from the frontend.
- Use independently collected reports as the team workflow. Proxy scanning is not included; historical proxy metadata is preserved, and old requests/jobs cannot silently become direct scans.
- Preserve existing reports with migration 10, which retains nullable historical transport metadata.

Validation details and remaining environment limitations are recorded in [docs/validation.md](docs/validation.md).
