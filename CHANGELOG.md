# Changelog

## 2026-11-02

- Add direct UDP scans using Nmap: common ports, Top 100 UDP and custom port lists.
- Preserve UDP `open|filtered` states during scanning, report import and export, including grouped Nmap results.
- Distinguish uncertain UDP observations from confirmed services in the evidence matrix and network map.
- Keep source, target and protocol controls in a compact row; move UDP details into the profile disclosure.
- Display port states in host cards and send custom UDP ports correctly from the frontend.
- Use independently collected reports as the team workflow. Proxy scanning is not included; historical proxy metadata is preserved, and old requests/jobs cannot silently become direct scans.
- Preserve existing reports with migration 10, which retains nullable historical transport metadata.

Validation details and remaining environment limitations are recorded in [docs/validation.md](docs/validation.md).
