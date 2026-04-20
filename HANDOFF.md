# Handoff — IPCONNEX-Telephony

## Last Session
- **Date:** 2026-04-19
- **Who:** Claude (Sonnet 4.6)
- **What was done:** Built full Frappe app from scratch — 4 DocTypes, 3 utility modules, 1 Script Report, hooks, scaffold
- **What's next:** Implement `_parse_acr_response()` once ACR access method confirmed, then deploy to bench
- **Known issues:** ACR scraper returns empty list — parse logic is a stub pending ACR format confirmation

## Previous Sessions
<!-- none -->

## Environment Notes
- App lives at `ipconnex_telephony/` inside project root
- Install on bench: `bench get-app /path/to/ipconnex_telephony && bench --site <site> install-app ipconnex_telephony`
- Scheduler hooks: daily sync + gain aggregation + invoice generation

## Access & Credentials
- Infisical project: `IPCONNEX Telephony`
- Environment: `Frappe ERPNext`
