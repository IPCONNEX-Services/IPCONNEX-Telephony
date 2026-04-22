# IPCONNEX Telephony — Architecture

## System Diagram

```
  IXC / ACR Platform (sip-gw)
  /system_reports/traffic_flow_report
            │
            │  HTTP scrape (scheduled)
            ▼
  ┌──────────────────────────────────────────────────────────┐
  │                   ipconnex_telephony (Frappe app)        │
  │                                                          │
  │  utils/acr_scraper.py   ──► Call Quality Summary        │
  │  utils/ixc_scraper.py   ──► Daily Gain Summary          │
  │                              │                           │
  │  utils/invoice_generator.py ◄┘                          │
  │       │                                                  │
  │       ├──► Sales Invoice   (customer leg)               │
  │       └──► Purchase Invoice (supplier leg)              │
  │                                                          │
  │  utils/infisical.py  (optional — reads scraper creds)   │
  └──────────────────────────────────────────────────────────┘
            │
            ▼
  ERPNext (Frappe bench) — MariaDB
```

## Components

| Component | Responsibility | Location |
| --- | --- | --- |
| **Telephony Settings** | Single-instance config: IXC URL, scraper credentials, Infisical references, sync interval | `doctype/telephony_settings/` |
| **Telephony Partner Contract** | One contract per partner (customer-only, supplier-only, or dual-leg interconnect). Controls billing cycle and invoice destination accounts. | `doctype/telephony_partner_contract/` |
| **Daily Gain Summary** | Aggregated revenue per customer per day (synced from IXC Originated rows) | `doctype/daily_gain_summary/` |
| **Call Quality Summary** | ASR/ACD/duration per supplier per destination per day (synced from IXC/ACR Terminated rows) | `doctype/call_quality_summary/` |
| **Invoice Generation Log** | One row per contract+direction+period. Tracks status (Pending / Success / Failed) and links to the generated invoice. | `doctype/invoice_generation_log/` |
| **Telephony Company Settings** | Per-company account mappings (receivable, payable, income, expense) used when generating invoices | `doctype/telephony_company_settings/` |
| **Telephony Sales Manager** | Lookup table mapping sales manager names to ERPNext User links | `doctype/telephony_sales_manager/` |
| **Rate Task / Telephony Ticket** | Lightweight task and ticket tracking for rate negotiations and support | `doctype/rate_task/`, `doctype/telephony_ticket/` |
| **ACR Scraper** (`utils/acr_scraper.py`) | Fetches terminator traffic from `/system_reports/traffic_flow_report` with `only_terminators` params. Writes Call Quality Summary rows. | `utils/acr_scraper.py` |
| **IXC Scraper** (`utils/ixc_scraper.py`) | Fetches full traffic report (all parties) from the same endpoint with `only_successfull=1`. Writes Daily Gain Summary + Call Quality Summary. | `utils/ixc_scraper.py` |
| **Scraping / Common** (`scraping/common.py`) | Shared session management, HTML parsing, and type coercion used by feature-level scraping modules in `scraping/` | `scraping/common.py` |
| **Invoice Generator** (`utils/invoice_generator.py`) | Daily billing cycle: for each active contract, emits a Sales Invoice (customer leg) and/or Purchase Invoice (supplier leg) at period end. Separate retry pass for failed invoices. | `utils/invoice_generator.py` |
| **Infisical Helper** (`utils/infisical.py`) | Pulls scraper credentials from self-hosted Infisical. Falls back to DocType password field if env vars absent. Token-cached. | `utils/infisical.py` |
| **Reports** | Gain Analysis (revenue by customer/date) and ASR Analysis (quality by supplier/country/date) | `report/gain_analysis/`, `report/asr_analysis/` |

## Data Flow

### Daily Sync (IXC — runs on `all` scheduler hook)

```
IXC /traffic_flow_report
  └─► ixc_scraper.sync_ixc_stats()
        ├─► parse Originated rows  ──► upsert Daily Gain Summary (per customer)
        └─► parse Terminated rows  ──► upsert Call Quality Summary (per supplier/country)
```

### Daily Sync (ACR — terminator-only, same scheduler hook)

```
ACR /traffic_flow_report  (values[terminator_tf_id][]=only_terminators)
  └─► acr_scraper.sync_call_records()
        └─► parse Terminated rows  ──► upsert Call Quality Summary (per supplier/country)
```

Both scrapers use the same `resolve_scraper_password()` function: Infisical → DocType fallback.

### Daily Billing (runs on `daily` scheduler hook)

```
invoice_generator.run_billing_cycle()
  └─► for each active Telephony Partner Contract at period end:
        ├─► customer leg → aggregate Daily Gain Summary → Sales Invoice
        └─► supplier leg → aggregate Call Quality Summary → Purchase Invoice
            (each leg gets its own Invoice Generation Log entry)

invoice_generator.retry_failed_invoices()
  └─► re-processes any Invoice Generation Log rows in Failed status
```

### Credential Resolution

```
resolve_scraper_password(settings)
  ├─► settings.scraper_password_secret_key present?
  │     └─► infisical.get_secret(key, project_slug, environment)
  │           ├─► _get_token()  (cached, refreshes 60s before expiry)
  │           └─► GET /api/v3/secrets/raw/{key}
  └─► fallback: settings.get_password("scraper_password")
```

## Infrastructure

- **Target type:** LXC on Proxmox
- **SSH user:** root
- **Service manager:** systemd
- **Service name:** frappe-bench
- **Platform:** Frappe v15 + ERPNext v15, MariaDB 10.x
- **Secrets:** Self-hosted Infisical — env vars `INFISICAL_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET` set on the bench environment

## Scheduler Hooks Summary

| Hook | Function | Purpose |
| --- | --- | --- |
| `all` | `ixc_scraper.sync_ixc_stats` | Scrape IXC traffic (respects `sync_interval_minutes`) |
| `daily` | `invoice_generator.run_billing_cycle` | Generate period-end invoices |
| `daily` | `invoice_generator.retry_failed_invoices` | Retry failed invoice attempts |
