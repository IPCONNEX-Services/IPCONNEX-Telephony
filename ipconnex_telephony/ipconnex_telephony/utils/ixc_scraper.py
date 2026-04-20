"""
IXC scraper — scrapes ipconnex.ixc.ua/system_reports/traffic_flow_report.

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
from frappe.utils import now_datetime, today, getdate

from ipconnex_telephony.utils.acr_scraper import resolve_scraper_password

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

IXC_LOGIN_PATH   = "/login/login"
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
    if not settings.get("ixc_url") or not settings.get("scraper_username") or not resolve_scraper_password(settings):
        frappe.logger().info("IXC sync skipped: ixc_url or scraper credentials not configured")
        return

    target_date = getdate(today()) - timedelta(days=1)
    session = _login(settings)
    references = _fetch_references(session, settings)
    html = _fetch_report(session, settings, target_date, target_date)
    parsed = _parse_traffic(html)

    _upsert_gain_summaries(parsed["customers"], references, target_date)
    _upsert_quality_summaries(parsed["suppliers"], references, target_date)

    frappe.db.set_value("Telephony Settings", "Telephony Settings", "last_gain_sync", now_datetime())
    frappe.db.commit()
    frappe.logger().info(
        f"IXC sync {target_date}: "
        f"{len(parsed['customers'])} customers, {len(parsed['suppliers'])} suppliers"
    )


# ---------------------------------------------------------------------------
# IXC session
# ---------------------------------------------------------------------------

def _login(settings):
    base = settings.ixc_url.rstrip("/")
    url = base + IXC_LOGIN_PATH
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
    if "Logout" not in str(response.content):
        frappe.throw("IXC login failed — check credentials in Telephony Settings")
    return session


def _fetch_references(session, settings):
    """
    Returns {ixc_name: erp_name} from the IXC customers table.
    Column 0 = IXC internal name, Column 1 = ERP customer/supplier name.
    """
    response = session.get(settings.ixc_url.rstrip("/") + IXC_REFS_PATH, verify=False)
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


def _fetch_report(session, settings, from_date: date, to_date: date) -> str:
    url = (
        settings.ixc_url.rstrip("/") + IXC_REPORT_PATH
        + f"?utf8=%E2%9C%93"
        f"&from%5Bday%5D={from_date.day}"
        f"&from%5Bmonth%5D={from_date.month}"
        f"&from%5Byear%5D={from_date.year}"
        f"&from%5Bhour%5D=00&from%5Bminute%5D=0"
        f"&to%5Bday%5D={to_date.day}"
        f"&to%5Bmonth%5D={to_date.month}"
        f"&to%5Byear%5D={to_date.year}"
        f"&to%5Bhour%5D=23&to%5Bminute%5D=59"
        f"&min_attempts=0&currency=890355288"
        f"&values%5Bpayee_id%5D%5B%5D=all"
        f"&values%5Boriginator_id%5D%5B%5D=all"
        f"&values%5Bterminator_id%5D%5B%5D=all"
        f"&group_by=1&code=&tf_group_country=none&responsible=All&commit=Get+report"
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
        "customers": [{"name": ixc_name, "rows": [{country, attempts, duration, asr, acd, charges}]}],
        "suppliers": [{"name": ixc_name, "rows": [{country, attempts, duration, asr, acd, charges}]}],
      }
    """
    customers = []
    suppliers = []

    try:
        table_html = _extract_table(html)
        cleaned = re.sub(r'[^a-zA-Z0-9"<>/ \-!.]', '', table_html)
        soup = BeautifulSoup(cleaned, "html5lib")

        company_name = ""
        company_type = ""
        company_rows = []

        for tr in soup.find_all("tr"):
            cells = [td.text.strip() for td in tr.find_all("td")]
            if not cells:
                continue

            if cells[0] in TYPE_CELLS:
                company_type = cells[0]
                continue

            if cells[0] in SKIP_CELLS or len(cells) <= 1:
                if company_name:
                    _flush(company_name, company_type, company_rows, customers, suppliers)
                    company_name = ""
                    company_type = ""
                    company_rows = []
                continue

            idx = 0
            if not company_name:
                company_name = cells[0]
                company_type = cells[1] if len(cells) > 1 else ""
                idx = 2

            row = _parse_row(cells, idx)
            if row:
                company_rows.append(row)

        if company_name:
            _flush(company_name, company_type, company_rows, customers, suppliers)

    except Exception as e:
        frappe.logger().error(f"IXC traffic parse error: {e}")

    return {"customers": customers, "suppliers": suppliers}


def _parse_row(cells, idx):
    try:
        attempts = _int(cells[2 + idx])
        charges  = _float(cells[6 + idx])
        if attempts == 0 and charges == 0:
            return None
        return {
            "country":  cells[0 + idx],
            "attempts": attempts,
            "duration": _float(cells[3 + idx]),
            "asr":      _float(cells[4 + idx]),
            "acd":      _float(cells[5 + idx]),
            "charges":  charges,
        }
    except (IndexError, ValueError):
        return None


def _flush(name, ctype, rows, customers, suppliers):
    if not rows:
        return
    entry = {"name": name, "rows": rows}
    if ctype == "Originated":
        customers.append(entry)
    elif ctype == "Terminated":
        suppliers.append(entry)


# ---------------------------------------------------------------------------
# Upsert — Daily Gain Summary (customers / revenue)
# ---------------------------------------------------------------------------

def _upsert_gain_summaries(customer_data, references, target_date):
    for company in customer_data:
        erp_name = references.get(company["name"], company["name"])
        if not frappe.db.exists("Customer", erp_name):
            frappe.logger().warning(f"IXC: customer not in ERP — '{erp_name}'")
            continue

        contract_info = _get_contract_info(erp_name)
        rows = company["rows"]
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

        existing = frappe.db.get_value(
            "Daily Gain Summary",
            {"summary_date": target_date, "customer": erp_name},
            "name",
        )
        if existing:
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
    for company in supplier_data:
        erp_name = references.get(company["name"], company["name"])

        for row in company["rows"]:
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
    table_html = re.findall(TABLE_REGEX, html, re.IGNORECASE | re.DOTALL)[0]
    table_html = re.sub(r'(<[^>]+)\s+onmouseover="[^"]*"', r'\1', table_html)
    return re.sub(
        r'<div\b[^>]*style="display:\s*none;"[^>]*>.*?</div>',
        '',
        table_html,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _get_contract_info(customer):
    result = frappe.db.get_value(
        "Telephony Contract",
        customer,
        ["sales_manager", "company"],
        as_dict=True,
    )
    return result or {}


def _int(value):
    return int(str(value).replace(",", "").strip() or 0)


def _float(value):
    return float(str(value).replace(",", ".").strip() or 0)
