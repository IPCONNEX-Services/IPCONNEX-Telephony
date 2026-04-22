# Handoff — IPCONNEX Telephony

## Last Session

- **Date:** 2026-04-21
- **Who:** Claude (Sonnet 4.6)
- **What was done:**
  - Confirmed ACR access method: same `/system_reports/traffic_flow_report` endpoint as IXC, with `values[terminator_tf_id][]=only_terminators` and extended date params (`post[from_accounting_time(*i)]`, `from_period`, `to_period`, `native_time_zone=UTC`)
  - Rewrote `utils/acr_scraper.py` — replaced CDR stub with working terminator traffic scraper; now a GET request mirroring IXC's approach
  - Added zero-duration filter (`duration != 0`) to ACR and IXC flush steps
  - Security audit: removed hardcoded IP (`10.100.10.230`) from `infisical.py` docstring; extracted all inline currency literals (`890355288`) to named constants; confirmed no passwords or tokens in source
  - All 14 tests in `telephony-test/test_url_builders.py` pass against the live platform
  - Filled `docs/architecture/OVERVIEW.md`, `DECISIONS.md`, `HANDOFF.md`, `TODO.md`

- **What's next:** Deploy app to ERPNext bench, configure Telephony Settings, run end-to-end test
- **Known issues:** None — scraper is live-tested and working

## Previous Sessions

- **2026-04-20** — Dual-leg billing model, Invoice Generation Log, Telephony Company Settings, Infisical helper, list view polish
- **2026-04-19** — Frappe app scaffold, 4 DocTypes (Telephony Settings, Telephony Contract, Call Record, Daily Gain Summary), ACR/gain/invoice stubs

## Environment Notes

- App lives at `ipconnex_telephony/ipconnex_telephony/` inside project root
- Install on bench:
  ```bash
  bench get-app /path/to/ipconnex_telephony
  bench --site <site> install-app ipconnex_telephony
  bench migrate
  ```
- Test suite lives at `D:\AI CLAUDE Code\telephony-test\test_url_builders.py` (Windows dev machine — runs against live platform)
- Scheduler hooks: `sync_ixc_stats` on every tick (respects `sync_interval_minutes`), billing on daily

## Access & Credentials

- Infisical project: `IPCONNEX Telephony`
- Environment: `Frappe ERPNext`
- Required env vars on bench: `INFISICAL_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET`
- Fallback: `scraper_password` encrypted field on Telephony Settings

## Key Files

| File | Purpose |
| --- | --- |
| `utils/acr_scraper.py` | Terminator-only traffic scraper — GET with `only_terminators` |
| `utils/ixc_scraper.py` | Full traffic scraper — GET with `only_successfull=1` |
| `scraping/common.py` | Shared session, parser, type coercion for feature-level modules |
| `utils/infisical.py` | Infisical secret pull with token cache |
| `utils/invoice_generator.py` | Billing cycle — Sales + Purchase invoices per contract |
| `hooks.py` | Scheduler event registration |
