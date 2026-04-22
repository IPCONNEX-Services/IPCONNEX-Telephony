"""
ACR/IXC terminator scraper — fetches supplier traffic via the traffic flow report.

Login:    GET  {url}/login/login  (establishes session cookie)
          POST {url}/login/login  with name/password/commit=OK
Report:   GET  {url}/system_reports/traffic_flow_report  with date-range + terminator params

Parses the class="table" traffic table, keeps only Terminated rows with duration > 0.
"""

import frappe
from frappe.utils import now_datetime, get_datetime

import requests
from bs4 import BeautifulSoup
from datetime import datetime, date as date_type, timedelta

from ipconnex_telephony.utils.infisical import get_secret as infisical_get_secret


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ACR_LOGIN_PATH  = "/login/login"
ACR_REPORT_PATH = "/system_reports/traffic_flow_report"

# Platform currency ID — move to Telephony Settings.ixc_currency_id when configurable
ACR_CURRENCY_ID = "890355288"

# Map ACR column header text → Call Record field name.
# Adjust keys to match actual <th> text shown in the tablesorter table.
ACR_COLUMN_MAP = {
    "Call ID":          "acr_call_id",
    "Date":             "call_date",
    "Start Time":       "start_time",
    "Duration":         "duration_seconds",
    "Customer":         "customer",
    "Terminator":       "supplier",
    "Supplier":         "supplier",
    "Destination":      "destination_number",
    "Country":          "destination_country",
    "Buy Rate":         "buy_rate",
    "Sell Rate":        "sell_rate",
}


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------

def sync_call_records():
    settings = frappe.get_single("Telephony Settings")
    if not settings.is_active:
        return

    interval = (settings.sync_interval_minutes or 60)
    if settings.last_acr_sync:
        elapsed = (now_datetime() - get_datetime(settings.last_acr_sync)).total_seconds() / 60
        if elapsed < interval:
            return

    target_date = date_type.today() - timedelta(days=1)
    session  = _login(settings)
    raw_rows = _fetch_cdr_page(session, settings, target_date, target_date)
    records  = _parse_rows(raw_rows)

    inserted = 0
    for rec in records:
        if not rec.get("acr_call_id"):
            continue
        if frappe.db.exists("Call Record", {"acr_call_id": rec["acr_call_id"]}):
            continue
        frappe.get_doc({"doctype": "Call Record", **rec}).insert(ignore_permissions=True)
        inserted += 1

    frappe.db.set_value("Telephony Settings", "Telephony Settings", "last_acr_sync", now_datetime())
    frappe.db.commit()
    frappe.logger().info(f"ACR sync {target_date}: {inserted} new records")


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def get_login_url(settings) -> str:
    return (settings.url or "").rstrip("/") + ACR_LOGIN_PATH


def get_data_url(settings, from_date: date_type, to_date: date_type) -> str:
    fd, fm, fy = from_date.day, from_date.month, from_date.year
    td, tm, ty = to_date.day,   to_date.month,   to_date.year
    base = (settings.url or "").rstrip("/")
    return (
        base + ACR_REPORT_PATH
        + f"?utf8=%E2%9C%93"
        f"&from%5Bday%5D={fd}&from%5Bmonth%5D={fm}&from%5Byear%5D={fy}"
        f"&from%5Bhour%5D=0&from%5Bminute%5D=0"
        f"&to%5Bday%5D={td}&to%5Bmonth%5D={tm}&to%5Byear%5D={ty}"
        f"&to%5Bhour%5D=23&to%5Bminute%5D=59"
        f"&post%5Bfrom_accounting_time%281i%29%5D={fy}"
        f"&post%5Bfrom_accounting_time%282i%29%5D={fm}"
        f"&post%5Bfrom_accounting_time%283i%29%5D={fd}"
        f"&post%5Bfrom_accounting_time%284i%29%5D=00"
        f"&post%5Bfrom_accounting_time%285i%29%5D=0"
        f"&post%5Bto_accounting_time%281i%29%5D={ty}"
        f"&post%5Bto_accounting_time%282i%29%5D={tm}"
        f"&post%5Bto_accounting_time%283i%29%5D={td}"
        f"&post%5Bto_accounting_time%284i%29%5D=23"
        f"&post%5Bto_accounting_time%285i%29%5D=59"
        f"&min_attempts=0&currency={ACR_CURRENCY_ID}"
        f"&values%5Bpayee_id%5D%5B%5D=all"
        f"&values%5Boriginator_id%5D%5B%5D=all"
        f"&values%5Boriginator_tf_id%5D%5B%5D=all"
        f"&values%5Bterminator_id%5D%5B%5D=all"
        f"&values%5Bterminator_tf_id%5D%5B%5D=only_terminators"
        f"&group_by=1&code=&tf_group_country=none&group_country=none"
        f"&responsible=All&sort=out_price&show_connect_price=1"
        f"&native_time_zone=UTC"
        f"&from_period={fy}-{fm:02d}-{fd:02d}+00%3A00%3A00+UTC"
        f"&to_period={ty}-{tm:02d}-{td:02d}+23%3A59%3A00+UTC"
        f"&commit=Get+report"
    )


# ---------------------------------------------------------------------------
# Web session
# ---------------------------------------------------------------------------

def _login(settings):
    login_url = get_login_url(settings)
    session   = requests.Session()
    session.get(login_url, verify=False, timeout=30)
    r = session.post(
        login_url,
        data={
            "name":     settings.scraper_username,
            "password": resolve_scraper_password(settings),
            "commit":   "OK",
        },
        verify=False,
        timeout=30,
    )
    if "Logout" not in r.text:
        frappe.throw("ACR login failed — check credentials in Telephony Settings")
    return session


def resolve_scraper_password(settings):
    """Public helper — shared by ACR and IXC scrapers. Tries Infisical, falls back to DocType."""
    secret_key = getattr(settings, "scraper_password_secret_key", None)
    if secret_key:
        secret = infisical_get_secret(
            secret_key,
            project_slug=settings.infisical_project_slug,
            environment=settings.infisical_environment or "prod",
        )
        if secret:
            return secret
    return settings.get_password("scraper_password") if settings.get("scraper_password") else None


def _fetch_cdr_page(session, settings, from_date: date_type, to_date: date_type):
    import re
    resp = session.get(
        get_data_url(settings, from_date, to_date),
        verify=False,
        timeout=60,
    )
    resp.raise_for_status()

    matches = re.findall(
        r'<table[^>]*class="table"[^>]*>.*?</table>',
        resp.text, re.IGNORECASE | re.DOTALL,
    )
    if not matches:
        frappe.logger().warning("ACR scraper: no traffic table found on terminator report page.")
        return []

    tbl = re.sub(r'(<[^>]+)\s+onmouseover="[^"]*"', r'\1', matches[0])
    tbl = re.sub(r'<div[^>]*style="display:\s*none;"[^>]*>.*?</div>', '', tbl,
                 flags=re.IGNORECASE | re.DOTALL)
    soup = BeautifulSoup(tbl, "html5lib")

    FLUSH = {"", "Total", "Total:", "Local sum", "Local sum:", "Profit", "Margin", "Markup"}
    SKIP  = {"Payee"}

    def _cell(td):
        return next((t.strip() for t in td.strings if t.strip()), "")

    rows = []
    company_name = ""
    company_rows = []

    def _flush():
        if company_name and company_rows:
            nz = [r for r in company_rows
                  if _float(r["duration"]) != 0]
            if nz:
                rows.extend(nz)

    for tr in soup.find_all("tr"):
        line = [_cell(td) for td in tr.find_all("td")]
        if not line:
            continue
        first = line[0]
        if first in SKIP:
            continue
        if first in FLUSH:
            _flush()
            company_name = ""
            company_rows = []
            continue
        if first == "Terminated":
            try:
                company_rows.append({
                    "supplier":  company_name,
                    "country":   line[1],
                    "attempts":  line[3],
                    "duration":  line[4],
                    "asr":       line[5],
                    "acd":       line[6],
                    "charges":   line[7],
                })
            except IndexError:
                pass
            continue
        if first == "Originated":
            _flush()
            company_name = ""
            company_rows = []
            continue
        index = 0
        if not company_name:
            company_name = line[0]
            ctype = line[1] if len(line) > 1 else ""
            if ctype == "Originated":
                company_name = ""
                continue
            index = 2
        try:
            company_rows.append({
                "supplier":  company_name,
                "country":   line[0 + index],
                "attempts":  line[2 + index],
                "duration":  line[3 + index],
                "asr":       line[4 + index],
                "acd":       line[5 + index],
                "charges":   line[6 + index],
            })
        except IndexError:
            pass

    _flush()
    return rows


# ---------------------------------------------------------------------------
# Row parsing
# ---------------------------------------------------------------------------

def _parse_rows(raw_rows):
    records = []
    for raw in raw_rows:
        try:
            records.append(_parse_row(raw))
        except Exception as e:
            frappe.logger().warning(f"ACR scraper: skipping row {raw} — {e}")
    return records


def _parse_row(raw):
    mapped = {}
    for acr_col, field in ACR_COLUMN_MAP.items():
        if acr_col in raw:
            mapped[field] = raw[acr_col]

    return {
        "acr_call_id":          str(mapped["acr_call_id"]),
        "call_date":            _parse_date(mapped.get("call_date")),
        "start_time":           _parse_datetime(mapped.get("start_time"), mapped.get("call_date")),
        "duration_seconds":     _parse_duration(mapped.get("duration_seconds")),
        "customer":             mapped.get("customer", ""),
        "supplier":             mapped.get("supplier", ""),
        "destination_number":   mapped.get("destination_number", ""),
        "destination_country":  mapped.get("destination_country", ""),
        "buy_rate":             _parse_float(mapped.get("buy_rate", "0")),
        "sell_rate":            _parse_float(mapped.get("sell_rate", "0")),
    }


# ---------------------------------------------------------------------------
# Type coercions
# ---------------------------------------------------------------------------

def _parse_date(value):
    """Accept YYYY-MM-DD or DD/MM/YYYY."""
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unrecognised date format: {value!r}")


def _parse_datetime(time_value, date_value):
    """Combine a date string + HH:MM:SS time string into a datetime."""
    if not time_value:
        return None
    d = _parse_date(date_value)
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            t = datetime.strptime(time_value, fmt).time()
            return datetime.combine(d, t) if d else None
        except ValueError:
            continue
    # If the ACR puts a full datetime in one cell, try that
    for fmt in ("%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(time_value, fmt)
        except ValueError:
            continue
    return None


def _parse_duration(value):
    """Accept seconds (int string) or HH:MM:SS."""
    if not value:
        return 0
    if ":" in str(value):
        parts = str(value).split(":")
        parts = [int(p) for p in parts]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
    return int(float(value))


def _parse_float(value):
    s = str(value).strip()
    s = s.replace(',', '') if '.' in s else s.replace(',', '.')
    try:
        return float(s or 0)
    except ValueError:
        return 0.0


