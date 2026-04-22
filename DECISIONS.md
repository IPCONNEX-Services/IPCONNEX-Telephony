# Architecture Decisions — IPCONNEX Telephony

Record important decisions so the team knows *why* things are the way they are.

---

## ADR-001: Dual-leg billing model (interconnect / swap)

- **Date:** 2026-04-20
- **Status:** accepted
- **Context:** Some partners are both customers (paying for origination) and suppliers (receiving payment for termination) under the same agreement — common in SIP interconnect / traffic-swap deals. Finance needs to net these or at least track both legs separately.
- **Decision:** `Telephony Partner Contract` has both a `customer` and a `supplier` link field. Both can be set on the same contract, producing a Sales Invoice (customer leg) and a Purchase Invoice (supplier leg) independently per billing cycle.
- **Alternatives:** Separate contracts for each direction — rejected because it doubles admin and breaks the netting view.
- **Consequences:** Invoice generator must handle both legs per contract. A failure on one leg must not block the other. `Invoice Generation Log` is keyed by `(contract, direction, period)` to track each leg independently.

---

## ADR-002: Shared scraper credentials (ACR + IXC use same login)

- **Date:** 2026-04-20
- **Status:** accepted
- **Context:** ACR (terminator-only report) and IXC (full traffic report) both live on the same platform with the same login page (`/login/login`). Maintaining separate credentials would add admin overhead with no security benefit.
- **Decision:** Single `scraper_username` / `scraper_password` on `Telephony Settings`, shared by both scrapers. `resolve_scraper_password()` in `acr_scraper.py` is the single resolution point used by both.
- **Alternatives:** Separate username/password fields per scraper — rejected as unnecessary given shared platform.
- **Consequences:** If the shared account's password changes, one update covers both scrapers.

---

## ADR-003: Same HTTP endpoint for both IXC and ACR scraping

- **Date:** 2026-04-21
- **Status:** accepted
- **Context:** Initial design assumed ACR used `/originator_calls` (a CDR-level endpoint) while IXC used `/system_reports/traffic_flow_report`. In practice, `/originator_calls` returns 404. The correct ACR endpoint is the same traffic flow report but with terminator-specific GET parameters.
- **Decision:** Both scrapers use `GET /system_reports/traffic_flow_report`. The ACR URL adds `values[terminator_tf_id][]=only_terminators`, extended `post[from_accounting_time(*i)]` date params, `sort=out_price`, `show_connect_price=1`, `native_time_zone=UTC`, and `from_period`/`to_period` strings. The IXC URL uses `only_successfull=1` instead.
- **Alternatives:** Using a hypothetical REST API — rejected because no API was confirmed to exist; scraping the existing web UI is the only confirmed working method.
- **Consequences:** HTML parsing logic is essentially shared. `scraping/common.py` holds the shared parser. Both scrapers apply the same FLUSH/SKIP/TYPES row classification pattern. Zero-duration rows are filtered out before any row is persisted.

---

## ADR-004: Infisical for secrets with DocType fallback

- **Date:** 2026-04-20
- **Status:** accepted
- **Context:** Hardcoding credentials or relying solely on Frappe's encrypted password field creates risk if the DB is exported or a non-admin sees the DocType. A secrets manager is safer, but we can't require it for every deployment (e.g., dev bench).
- **Decision:** `utils/infisical.py` provides `get_secret()`. `resolve_scraper_password()` calls Infisical first (if `scraper_password_secret_key` is set and env vars are present), then falls back to `settings.get_password("scraper_password")`. No exception is raised for missing env vars — callers receive `None` and fall back silently.
- **Alternatives:** Env-var only (no DocType field) — rejected because it breaks the ERPNext admin UX. Infisical only — rejected because dev environments may not have an Infisical instance.
- **Consequences:** The bench must have `INFISICAL_URL`, `INFISICAL_CLIENT_ID`, `INFISICAL_CLIENT_SECRET` set for secret pull to work. Access token is module-level cached with 60-second expiry buffer to avoid repeated auth calls.

---

## ADR-005: Currency ID as named constant, not a Telephony Settings field

- **Date:** 2026-04-21
- **Status:** accepted (candidate for promotion to settings field)
- **Context:** The IXC platform uses an internal numeric currency ID (`890355288`) in report URLs. Initially this was inlined as a literal integer in three places.
- **Decision:** Extracted to named constants — `ACR_CURRENCY_ID` in `acr_scraper.py`, `IXC_CURRENCY_ID` in `ixc_scraper.py`, `CURRENCY_ID` in `scraping/common.py`. Not moved to `Telephony Settings` yet because it has never needed to change.
- **Alternatives:** Add `ixc_currency_id` field to `Telephony Settings` — deferred; implement when a second currency or tenant is needed.
- **Consequences:** If the platform currency ID ever changes, one constant per file needs updating. If multiple currencies or tenants are needed, promote to the settings DocType.

---

## ADR-006: Zero-duration filter on scraped rows

- **Date:** 2026-04-21
- **Status:** accepted
- **Context:** The platform's traffic report includes rows where `duration = 0` (unanswered calls only). Persisting these inflates attempt counts and produces division-by-zero in ACD calculations.
- **Decision:** Both ACR and IXC scrapers filter out rows where `duration == 0` before building any summary records. Filter is applied in the flush step (`_flush()` / `flush_block()`).
- **Alternatives:** Filter at aggregation time — rejected because it's cleaner to exclude at ingest and avoids storing useless rows.
- **Consequences:** Attempt counts in `Call Quality Summary` only reflect calls with non-zero duration. Pure-seizure stats (zero-duration) are not available from this data source.

---

<!-- Copy the template above for each new decision -->
