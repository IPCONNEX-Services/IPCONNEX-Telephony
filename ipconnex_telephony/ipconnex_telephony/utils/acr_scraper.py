"""
ACR call record scraper — incremental web UI scraping.

Login flow:  POST {acr_url}/index.php  (or /login — adjust ACR_LOGIN_PATH)
CDR page:    GET  {acr_url}/cdr.php    (or /cdr  — adjust ACR_CDR_PATH)

Column mapping: ACR_COLUMN_MAP maps ACR table header text → our field name.
Adjust the keys to match the exact column headers shown in the ACR CDR table.
"""

import frappe
from frappe.utils import now_datetime

import requests
from bs4 import BeautifulSoup
from datetime import datetime, date as date_type

from ipconnex_telephony.utils.infisical import get_secret as infisical_get_secret


# ---------------------------------------------------------------------------
# Adjust these to match your ACR installation
# ---------------------------------------------------------------------------

ACR_LOGIN_PATH = "/index.php"
ACR_CDR_PATH = "/cdr.php"

# Map ACR column header text → Call Record field name.
# Keys must exactly match what appears in the <th> cells of the CDR table.
ACR_COLUMN_MAP = {
    "Call ID":          "acr_call_id",
    "Date":             "call_date",
    "Start Time":       "start_time",
    "Duration":         "duration_seconds",
    "Customer":         "customer",
    "Supplier":         "supplier",
    "Destination":      "destination_number",
    "Country":          "destination_country",
    "Buy Rate":         "buy_rate",
    "Sell Rate":        "sell_rate",
}

# Login form field names (inspect the ACR login page to confirm)
ACR_LOGIN_FIELDS = {
    "username_field": "username",
    "password_field": "password",
}


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------

def sync_call_records():
    settings = frappe.get_single("Telephony Settings")
    if not settings.is_active:
        return

    last_id = _get_last_synced_id()
    session = _login(settings)
    raw_rows = _fetch_cdr_page(session, settings, since_id=last_id)
    records = _parse_rows(raw_rows)

    inserted = 0
    for rec in records:
        if frappe.db.exists("Call Record", rec["acr_call_id"]):
            continue
        frappe.get_doc({"doctype": "Call Record", **rec}).insert(ignore_permissions=True)
        inserted += 1

    frappe.db.commit()
    frappe.logger().info(f"ACR sync: {inserted} new records (since id={last_id})")


# ---------------------------------------------------------------------------
# Web session
# ---------------------------------------------------------------------------

def _login(settings):
    session = requests.Session()
    session.post(
        settings.acr_url.rstrip("/") + ACR_LOGIN_PATH,
        data={
            ACR_LOGIN_FIELDS["username_field"]: settings.scraper_username,
            ACR_LOGIN_FIELDS["password_field"]: resolve_scraper_password(settings),
        },
        timeout=30,
    )
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


def _fetch_cdr_page(session, settings, since_id=None):
    params = {}
    if since_id:
        params["since_id"] = since_id

    resp = session.get(
        settings.acr_url.rstrip("/") + ACR_CDR_PATH,
        params=params,
        timeout=60,
    )
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "lxml")
    table = soup.find("table")
    if not table:
        frappe.logger().warning("ACR scraper: no <table> found on CDR page.")
        return []

    headers = [th.get_text(strip=True) for th in table.find("tr").find_all(["th", "td"])]
    rows = []
    for tr in table.find_all("tr")[1:]:  # skip header row
        cells = [td.get_text(strip=True) for td in tr.find_all("td")]
        if cells:
            rows.append(dict(zip(headers, cells)))

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
    return float(str(value).replace(",", ".").strip() or 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_last_synced_id():
    result = frappe.db.sql(
        "SELECT acr_call_id FROM `tabCall Record` ORDER BY call_date DESC, start_time DESC LIMIT 1"
    )
    return result[0][0] if result else None
