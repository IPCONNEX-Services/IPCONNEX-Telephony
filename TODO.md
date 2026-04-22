# Project: IPCONNEX-Telephony

## Current Phase

Scraper confirmed working against live platform. Ready for bench deployment and end-to-end billing test.

## Active Tasks

- [ ] Deploy app to bench (`bench get-app` / `bench install-app ipconnex_telephony` / `bench migrate`)
- [ ] Set env vars on bench: `INFISICAL_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET`
- [ ] Configure Telephony Settings singleton:
      - `url` — IXC/ACR platform base URL
      - `scraper_username`, `scraper_password` (or `scraper_password_secret_key` for Infisical)
      - `infisical_project_slug`, `infisical_environment`
      - `sync_interval_minutes` (default 60)
- [ ] Seed `Telephony Sales Manager` records
- [ ] Seed `Telephony Company Settings` per company (receivable / payable / income / expense accounts)
- [ ] Create `Telephony Partner Contract` per partner (customer-only, supplier-only, or dual-leg)
- [ ] End-to-end test: IXC sync → Daily Gain Summary → billing cycle → Sales Invoice (customer leg)
- [ ] End-to-end test: ACR sync → Call Quality Summary → billing cycle → Purchase Invoice (supplier leg)
- [ ] Verify retry pass: `retry_failed_invoices()` re-processes Failed log entries
- [ ] Consider promoting `ACR_CURRENCY_ID` / `IXC_CURRENCY_ID` to `Telephony Settings.ixc_currency_id` field if multiple currencies or tenants are needed

## Blocked

- Nothing currently blocked

## Completed

- [2026-04-19] Frappe app scaffold (setup.py, hooks.py, modules.txt)
- [2026-04-19] DocTypes: Telephony Settings, Telephony Partner Contract, Call Record, Daily Gain Summary
- [2026-04-19] Utilities: ACR scraper stub, gain aggregator, invoice generator, quality aggregator
- [2026-04-19] Report: Gain Analysis (filterable by date, customer, supplier)
- [2026-04-20] Dual-leg billing — Telephony Partner Contract supports customer + supplier on the same contract (interconnect/netting)
- [2026-04-20] Invoice generator emits Sales Invoice (customer leg) + Purchase Invoice (supplier leg) independently per period
- [2026-04-20] New DocType: Telephony Sales Manager (replaces Sales Person link)
- [2026-04-20] Call Quality Summary DocType for ASR/ACD per supplier/country/day
- [2026-04-20] Invoice Generation Log keyed by direction (Customer / Supplier)
- [2026-04-20] Telephony Company Settings adds payable_account + expense_account for Purchase Invoice leg
- [2026-04-20] Unified scraper credentials on Telephony Settings (shared by ACR + IXC)
- [2026-04-20] Infisical helper (`utils/infisical.py`) — optional runtime secret pull with DocType fallback
- [2026-04-20] List views tightened across all DocTypes
- [2026-04-21] ACR access method confirmed — same `/system_reports/traffic_flow_report` endpoint as IXC
- [2026-04-21] `utils/acr_scraper.py` rewritten — GET with `values[terminator_tf_id][]=only_terminators`; zero-duration filter; live-tested (14/14 tests passing)
- [2026-04-21] Security audit — removed hardcoded IP from infisical.py docstring; extracted `890355288` currency literals to named constants
- [2026-04-21] Architecture docs filled: OVERVIEW.md, DECISIONS.md, HANDOFF.md, TODO.md
