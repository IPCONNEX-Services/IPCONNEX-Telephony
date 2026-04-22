"""
IXC scraper — scrapes {url}/system_reports/traffic_flow_report (url from Telephony Settings).

IXC provides aggregated data (not individual CDRs):
  Originated rows = customers  → revenue/charges per country
  Terminated rows = suppliers  → ASR/ACD/attempts per country

Column layout per country row (offset by `idx`):
  [0+idx]  country
  [2+idx]  attempts / seizures
  [3+idx]  duration (minutes)
  [4+idx]  ASR %
  [5+idx]  ACD (seconds)
  [6+idx]  charges (USD)

Reference table from /customers maps IXC internal names to ERP names.
"""

import re
import frappe
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import date, timedelta
from frappe.utils import now_datetime, getdate

from ipconnex_telephony.utils import utc_today, utc_now
from ipconnex_telephony.utils.acr_scraper import resolve_scraper_password

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

IXC_LOGIN_PATH   = "/login/login"
IXC_CURRENCY_ID  = "890355288"
IXC_REFS_PATH    = "/customers"
IXC_REPORT_PATH  = "/system_reports/traffic_flow_report"

TABLE_REGEX = r'<table[^>]*class="table"[^>]*>.*?</table>'
SKIP_CELLS  = {"", "Total", "Total:", "Local sum", "Profit", "Margin", "Markup"}
TYPE_CELLS  = {"Terminated", "Originated"}


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------

@frappe.whitelist()
def sync_ixc_stats():
    settings = frappe.get_single("Telephony Settings")
    if not settings.is_active:
        return

    target_date = utc_today() - timedelta(days=1)

    interval = (settings.sync_interval_minutes or 60)
    if settings.last_acr_sync:
        last_sync = getdate(settings.last_acr_sync)
        already_synced_today = last_sync >= target_date
        elapsed = (utc_now() - getdate(settings.last_acr_sync)).total_seconds() / 60
        if already_synced_today and elapsed < interval:
            return

    base_url = (settings.url or "").rstrip("/")
    if not base_url or not settings.get("scraper_username") or not resolve_scraper_password(settings):
        frappe.logger().info("IXC sync skipped: url or scraper credentials not configured")
        return
    session = _login(base_url, settings)
    references = _fetch_references(session, base_url)
    html = _fetch_report(session, base_url, target_date, target_date)
    parsed = _parse_traffic(html)

    _upsert_gain_summaries(parsed["customers"], references, target_date)
    _upsert_quality_summaries(parsed["suppliers"], references, target_date)

    frappe.db.set_value("Telephony Settings", "Telephony Settings", "last_acr_sync", utc_now())
    frappe.db.set_value("Telephony Settings", "Telephony Settings", "last_gain_sync", utc_now())
    frappe.db.commit()
    frappe.logger().info(
        f"IXC sync {target_date}: "
        f"{len(parsed['customers'])} customers, {len(parsed['suppliers'])} suppliers"
    )


# ---------------------------------------------------------------------------
# IXC session
# ---------------------------------------------------------------------------

def _login(base_url, settings):
    url = base_url + IXC_LOGIN_PATH
    session = requests.Session()
    response = session.get(url, verify=False)
    cookies = requests.utils.dict_from_cookiejar(response.cookies)
    response = session.post(
        url,
        data={
            "name":     settings.scraper_username,
            "password": resolve_scraper_password(settings),
            "commit":   "OK",
        },
        cookies=cookies,
        verify=False,
    )
    if "Logout" not in response.text:
        frappe.throw("IXC login failed — check credentials in Telephony Settings")
    return session


def _fetch_references(session, base_url):
    """
    Returns {ixc_name: erp_name} from the IXC customers table.
    Column 0 = IXC internal name, Column 1 = ERP customer/supplier name.
    """
    response = session.get(base_url + IXC_REFS_PATH, verify=False)
    try:
        table_html = _extract_table(response.text)
        soup = BeautifulSoup(table_html, "html5lib")
        ref_table = soup.find(id="customers-list")
        if not ref_table:
            return {}
        refs = {}
        for tr in ref_table.find_all("tr"):
            cells = [td.text.strip() for td in tr.find_all("td")]
            if len(cells) >= 2 and cells[1] and cells[0] not in ("", "Nyloo"):
                refs[cells[0]] = cells[1]  # IXC name → ERP name
        return refs
    except Exception as e:
        frappe.logger().warning(f"IXC: could not fetch references — {e}")
        return {}


def _fetch_report(session, base_url, from_date: date, to_date: date) -> str:
    url = (
        base_url + IXC_REPORT_PATH
        + f"?utf8=%E2%9C%93"
        f"&from%5Bday%5D={from_date.day}"
        f"&from%5Bmonth%5D={from_date.month}"
        f"&from%5Byear%5D={from_date.year}"
        f"&from%5Bhour%5D=00&from%5Bminute%5D=0"
        f"&to%5Bday%5D={to_date.day}"
        f"&to%5Bmonth%5D={to_date.month}"
        f"&to%5Byear%5D={to_date.year}"
        f"&to%5Bhour%5D=23&to%5Bminute%5D=59"
        f"&min_attempts=0&currency={IXC_CURRENCY_ID}"
        f"&values%5Bpayee_id%5D%5B%5D=all"
        f"&values%5Boriginator_id%5D%5B%5D=all"
        f"&values%5Bterminator_id%5D%5B%5D=all"
        f"&group_by=1&code=&tf_group_country=none&responsible=All&only_successfull=1&commit=Get+report"
    )
    response = session.get(url, verify=False)
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _parse_traffic(html: str) -> dict:
    """
    Returns:
      {
        "customers": {ixc_name: [{country, attempts, duration, asr, acd, charges}]},
        "suppliers": {ixc_name: [{country, attempts, duration, asr, acd, charges}]},
      }
    """
    customers = {}
    suppliers = {}

    try:
        table_html = _extract_table(html)
        if not table_html:
            frappe.logger().warning("IXC: no traffic table found in report HTML")
            return {"customers": {}, "suppliers": {}}
        soup = BeautifulSoup(table_html, "html5lib")

        FLUSH  = {"", "Total", "Total:", "Local sum", "Local sum:",
                  "Profit", "Margin", "Markup"}
        SKIP   = {"Payee"}
        TYPES  = {"Terminated", "Originated"}

        company_name = ""
        company_type = ""
        company_rows = []

        def _flush_block():
            if company_name and company_rows:
                target = customers if company_type == "Originated" else suppliers
                target.setdefault(company_name, []).extend(company_rows)

        def _cell(td):
            return next((t.strip() for t in td.strings if t.strip()), "")

        for tr in soup.find_all("tr"):
            line = [_cell(td) for td in tr.find_all("td")]
            if not line:
                continue

            first = line[0]

            if first in SKIP:
                continue

            if first in FLUSH:
                _flush_block()
                company_name = ""
                company_type = ""
                company_rows = []
                continue

            if first in TYPES:
                # same company switching type (e.g. ADCOM Originated → ADCOM Terminated)
                _flush_block()
                company_type = first
                company_rows = []
                # remainder of this row is the first country entry
                try:
                    company_rows.append({
                        "country":  line[1],
                        "attempts": _int(line[3]),
                        "duration": _float(line[4]),
                        "asr":      _float(line[5]),
                        "acd":      _float(line[6]),
                        "charges":  _float(line[7]),
                    })
                except (IndexError, ValueError):
                    pass
                continue

            # regular data row
            index = 0
            if company_name == "":
                company_name = line[0]
                company_type = line[1] if len(line) > 1 else ""
                index = 2
            try:
                company_rows.append({
                    "country":  line[0 + index],
                    "attempts": _int(line[2 + index]),
                    "duration": _float(line[3 + index]),
                    "asr":      _float(line[4 + index]),
                    "acd":      _float(line[5 + index]),
                    "charges":  _float(line[6 + index]),
                })
            except (IndexError, ValueError):
                pass

        _flush_block()

    except Exception as e:
        frappe.logger().error(f"IXC traffic parse error: {e}")

    return {"customers": customers, "suppliers": suppliers}


# ---------------------------------------------------------------------------
# Upsert — Daily Gain Summary (customers / revenue)
# ---------------------------------------------------------------------------

def _upsert_gain_summaries(customer_data, references, target_date):
    for ixc_name, rows in customer_data.items():
        erp_name = references.get(ixc_name, ixc_name)
        if not frappe.db.exists("Customer", erp_name):
            frappe.logger().warning(f"IXC: customer not in ERP — '{erp_name}'")
            continue

        contract_info = _get_contract_info(erp_name)
        total_revenue  = sum(r["charges"]  for r in rows)
        total_minutes  = sum(r["duration"] for r in rows)
        total_attempts = sum(r["attempts"] for r in rows)

        values = {
            "total_calls":      total_attempts,
            "total_minutes":    round(total_minutes, 2),
            "total_cost":       0,
            "total_revenue":    round(total_revenue, 4),
            "total_margin":     round(total_revenue, 4),
            "margin_percentage": 0,
            "sales_manager":    contract_info.get("sales_manager") or None,
            "company":          contract_info.get("company") or None,
        }

        existing, status = frappe.db.get_value(
            "Daily Gain Summary",
            {"summary_date": target_date, "customer": erp_name},
            ["name", "customer_invoice_status"],
        ) or (None, None)

        if existing:
            if status == "Invoiced":
                frappe.logger().info(f"IXC: skipping {erp_name} {target_date} — already invoiced")
                continue
            frappe.db.set_value("Daily Gain Summary", existing, values)
        else:
            frappe.get_doc({
                "doctype":      "Daily Gain Summary",
                "summary_date": target_date,
                "customer":     erp_name,
                **values,
            }).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Upsert — Call Quality Summary (suppliers / ASR)
# ---------------------------------------------------------------------------

def _upsert_quality_summaries(supplier_data, references, target_date):
    for ixc_name, rows in supplier_data.items():
        erp_name = references.get(ixc_name, ixc_name)

        for row in rows:
            answered = int(row["attempts"] * row["asr"] / 100) if row["asr"] else 0
            values = {
                "total_seizures":         row["attempts"],
                "answered_calls":         answered,
                "total_duration_seconds": int(row["duration"] * 60),
            }

            existing = frappe.db.get_value(
                "Call Quality Summary",
                {
                    "summary_date":      target_date,
                    "supplier":          erp_name,
                    "destination_country": row["country"],
                    "period":            "Daily",
                },
                "name",
            )
            if existing:
                doc = frappe.get_doc("Call Quality Summary", existing)
                doc.update(values)
                doc.save(ignore_permissions=True)
            else:
                frappe.get_doc({
                    "doctype":           "Call Quality Summary",
                    "summary_date":      target_date,
                    "customer":          "",
                    "supplier":          erp_name,
                    "destination_country": row["country"],
                    "period":            "Daily",
                    **values,
                }).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_table(html: str) -> str:
    matches = re.findall(TABLE_REGEX, html, re.IGNORECASE | re.DOTALL)
    if not matches:
        return ""
    table_html = matches[0]
    table_html = re.sub(r'(<[^>]+)\s+onmouseover="[^"]*"', r'\1', table_html)
    return re.sub(
        r'<div\b[^>]*style="display:\s*none;"[^>]*>.*?</div>',
        '',
        table_html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _get_contract_info(customer):
    result = frappe.db.get_value(
        "Telephony Partner Contract",
        {"customer": customer, "is_active": 1},
        ["sales_manager", "company"],
        as_dict=True,
    )
    return result or {}


def _int(value):
    return int(str(value).replace(",", "").strip() or 0)


def _float(value):
    return float(str(value).replace(",", ".").strip() or 0)
