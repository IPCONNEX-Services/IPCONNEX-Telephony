# Project: IPCONNEX-Telephony

## Current Phase
Dual-leg billing model in place. Ready for deployment on ERPNext bench, then end-to-end test with real ACR.

## Active Tasks
- [ ] Confirm ACR access method (web UI / REST API / DB export) and adjust `ACR_COLUMN_MAP` + `ACR_LOGIN_PATH` / `ACR_CDR_PATH` / `ACR_LOGIN_FIELDS` in `utils/acr_scraper.py`
- [ ] Set `INFISICAL_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET` on the bench environment (or local `.env`)
- [ ] Deploy app to bench (`bench get-app` / `bench install-app ipconnex_telephony` / `bench migrate`)
- [ ] Configure Telephony Settings singleton:
      - scraper_username, scraper_password (or scraper_password_secret_key for Infisical)
      - acr_url (required), ixc_url (optional)
      - infisical_project_slug, infisical_environment
- [ ] Seed `Telephony Sales Manager` records
- [ ] Seed `Telephony Company Settings` per company (receivable/payable/income/expense accounts)
- [ ] Create `Telephony Contract` per partner (customer-only, supplier-only, or dual-leg interconnect)
- [ ] End-to-end test: ACR sync → Call Records → daily aggregators → sales invoice (customer leg) → purchase invoice (supplier leg)
- [ ] Verify retry via `retry_failed_invoices()` for both legs

## Blocked
- ACR column mapping + login flow — blocked until ACR access method is confirmed
- IXC scraping — opt-in (leave `ixc_url` blank to disable); uses the same scraper credentials as ACR

## Completed
- [2026-04-19] Frappe app scaffold (setup.py, hooks.py, modules.txt)
- [2026-04-19] DocTypes: Telephony Settings, Telephony Contract, Call Record, Daily Gain Summary
- [2026-04-19] Utilities: ACR scraper (login/fetch/parse stubs), gain aggregator, invoice generator, quality aggregator
- [2026-04-19] Report: Gain Analysis (filterable by date, customer, supplier)
- [2026-04-20] Dual-leg billing — Telephony Contract supports customer + supplier on the same contract (interconnect/netting)
- [2026-04-20] Invoice generator emits Sales Invoice (customer leg) + Purchase Invoice (supplier leg) independently per period
- [2026-04-20] New DocType: Telephony Sales Manager (replaces Sales Person link)
- [2026-04-20] Call Record invoicing state split per direction (`customer_invoice_status`, `supplier_invoice_status`, `sales_invoice`, `purchase_invoice`); `is_excluded` flag for data hygiene
- [2026-04-20] Invoice Generation Log keyed by direction
- [2026-04-20] Telephony Company Settings adds payable_account + expense_account for Purchase Invoice leg
- [2026-04-20] Unified scraper credentials on Telephony Settings (shared by ACR + IXC)
- [2026-04-20] Infisical helper (`utils/infisical.py`) — optional runtime secret pull
- [2026-04-20] List views tightened across all DocTypes in the module
