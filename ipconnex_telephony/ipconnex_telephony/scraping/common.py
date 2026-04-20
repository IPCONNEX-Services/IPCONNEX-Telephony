"""
Shared IXC scraping utilities — session management, HTML parsing, type coercion.

All public functions return plain Python dicts/lists (JSON-serializable).
Credentials and base URL are read from the Telephony Settings single doctype.
"""

import re
import requests
import urllib3
from bs4 import BeautifulSoup
from datetime import date

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

LOGIN_PATH     = "/login/login"
CUSTOMERS_PATH = "/customers"
REPORT_PATH    = "/system_reports/traffic_flow_report"
BALANCE_PATH   = "/system_reports/balance_report"

TABLE_REGEX  = r'<table[^>]*class="table"[^>]*>.*?</table>'
_SKIP_CELLS  = {"", "Total", "Total:", "Local sum", "Profit", "Margin", "Markup"}
_TYPE_CELLS  = {"Terminated", "Originated"}


# ---------------------------------------------------------------------------
# IXCClient — shared context so each feature does not re-login
# ---------------------------------------------------------------------------

class IXCClient:
    """
    Holds an authenticated session + cached reference map.
    Pass one instance across multiple feature calls to avoid redundant HTTP trips.

    Usage:
        client = IXCClient.connect()
        gain   = get_gain_stats(client, from_date, to_date)
        asr    = get_asr_quality(client, from_date, to_date)
    """

    def __init__(self, session: requests.Session, references: dict, base_url: str):
        self.session    = session
        self.references = references  # {ixc_name: erp_name}
        self.base_url   = base_url

    @classmethod
    def connect(cls) -> "IXCClient":
        import frappe
        from ipconnex_telephony.utils.acr_scraper import resolve_scraper_password
        settings  = frappe.get_single("Telephony Settings")
        base_url  = (settings.ixc_url or "https://ipconnex.ixc.ua").rstrip("/")
        username  = settings.scraper_username
        password  = resolve_scraper_password(settings)
        session    = _do_login(username, password, base_url)
        references = _fetch_references(session, base_url)
        return cls(session, references, base_url)

    def resolve(self, ixc_name: str) -> str:
        return self.references.get(ixc_name, ixc_name)

    def fetch_traffic(self, from_date: date, to_date: date) -> dict:
        html = fetch_traffic_report(self.session, from_date, to_date, self.base_url)
        return parse_traffic(html)

    def fetch_balance_html(self) -> str:
        return fetch_balance_report(self.session, self.base_url)


# ---------------------------------------------------------------------------
# Low-level session helpers (used by IXCClient; also exported for direct use)
# ---------------------------------------------------------------------------

def _do_login(username: str, password: str, base_url: str) -> requests.Session:
    """
    Opens an authenticated IXC session.
    requests.Session tracks cookies automatically — no manual jar handling needed.
    Raises RuntimeError if 'Logout' is absent from the response (bad credentials).
    Use IXCClient.connect() as the public entry point.
    """
    url     = base_url + LOGIN_PATH
    session = requests.Session()
    session.get(url, verify=False)          # establishes CSRF / session cookie
    r = session.post(
        url,
        data={"name": username, "password": password, "commit": "OK"},
        verify=False,
    )
    if "Logout" not in str(r.content):
        raise RuntimeError("IXC login failed — check credentials in Telephony Settings")
    return session


def _fetch_references(session: requests.Session, base_url: str) -> dict:
    """
    Returns {ixc_name: erp_name} from the IXC /customers page.
    Parses the full page (not just the first class="table") so that
    the #customers-list element is always found regardless of page layout.
    """
    try:
        r    = session.get(base_url + CUSTOMERS_PATH, verify=False)
        soup = BeautifulSoup(r.text, "html5lib")
        tbl  = soup.find(id="customers-list")
        if not tbl:
            return {}
        refs = {}
        for tr in tbl.find_all("tr"):
            cells = [td.text.strip() for td in tr.find_all("td")]
            if len(cells) >= 2 and cells[1] and cells[0] not in ("", "Nyloo"):
                refs[cells[0]] = cells[1]
        return refs
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# HTTP fetchers
# ---------------------------------------------------------------------------

def fetch_traffic_report(session: requests.Session, from_date: date, to_date: date, base_url: str) -> str:
    """Fetches the raw HTML of the IXC traffic flow report for the given date range."""
    params = (
        f"?utf8=%E2%9C%93"
        f"&from%5Bday%5D={from_date.day}&from%5Bmonth%5D={from_date.month}&from%5Byear%5D={from_date.year}"
        f"&from%5Bhour%5D=00&from%5Bminute%5D=0"
        f"&to%5Bday%5D={to_date.day}&to%5Bmonth%5D={to_date.month}&to%5Byear%5D={to_date.year}"
        f"&to%5Bhour%5D=23&to%5Bminute%5D=59"
        f"&min_attempts=0&currency=890355288"
        f"&values%5Bpayee_id%5D%5B%5D=all"
        f"&values%5Boriginator_id%5D%5B%5D=all"
        f"&values%5Bterminator_id%5D%5B%5D=all"
        f"&group_by=1&code=&tf_group_country=none&responsible=All&commit=Get+report"
    )
    r = session.get(base_url + REPORT_PATH + params, verify=False)
    r.raise_for_status()
    return r.text


def fetch_balance_report(session: requests.Session, base_url: str) -> str:
    """Fetches the raw HTML of the IXC balance report."""
    r = session.get(base_url + BALANCE_PATH, verify=False)
    r.raise_for_status()
    return r.text


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------

def parse_traffic(html: str) -> dict:
    """
    Parses the traffic flow report HTML into structured dicts.

    Returns:
      {
        "customers": [{"name": str, "rows": [<row_dict>]}],   # Originated
        "suppliers": [{"name": str, "rows": [<row_dict>]}],   # Terminated
      }

    Row dict keys: country, attempts, duration (min), asr (%), acd (s), charges (USD).
    """
    customers: list = []
    suppliers: list = []

    table_html = _extract_traffic_table(html)
    cleaned    = re.sub(r'[^a-zA-Z0-9"<>/ \-!.]', '', table_html)
    soup       = BeautifulSoup(cleaned, "html5lib")

    company_name = ""
    company_type = ""
    company_rows: list = []

    for tr in soup.find_all("tr"):
        cells = [td.text.strip() for td in tr.find_all("td")]
        if not cells:
            continue

        if cells[0] in _TYPE_CELLS:
            company_type = cells[0]
            continue

        if cells[0] in _SKIP_CELLS or len(cells) <= 1:
            if company_name:
                _flush(company_name, company_type, company_rows, customers, suppliers)
                company_name = ""
                company_type = ""
                company_rows = []
            continue

        idx = 0
        if not company_name:
            company_name = cells[0]
            company_type = cells[1] if len(cells) > 1 else company_type
            idx = 2

        row = _parse_row(cells, idx)
        if row:
            company_rows.append(row)

    if company_name:
        _flush(company_name, company_type, company_rows, customers, suppliers)

    return {"customers": customers, "suppliers": suppliers}


# ---------------------------------------------------------------------------
# Internal parsing helpers
# ---------------------------------------------------------------------------

def _extract_traffic_table(html: str) -> str:
    """Extracts and sanitises the first class='table' element from the HTML."""
    tables = re.findall(TABLE_REGEX, html, re.IGNORECASE | re.DOTALL)
    if not tables:
        raise ValueError("No class='table' element found in report HTML")
    tbl = re.sub(r'(<[^>]+)\s+onmouseover="[^"]*"', r'\1', tables[0])
    return re.sub(
        r'<div\b[^>]*style="display:\s*none;"[^>]*>.*?</div>',
        '',
        tbl,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _parse_row(cells: list, idx: int) -> dict | None:
    """
    Extracts one country row.
    Column layout (offset by idx):
      [0] country  [2] attempts  [3] duration(min)  [4] ASR%  [5] ACD(s)  [6] charges
    Returns None for zero-traffic rows.
    """
    try:
        attempts = to_int(cells[2 + idx])
        charges  = to_float(cells[6 + idx])
        if attempts == 0 and charges == 0:
            return None
        return {
            "country":  cells[idx],
            "attempts": attempts,
            "duration": to_float(cells[3 + idx]),
            "asr":      to_float(cells[4 + idx]),
            "acd":      to_float(cells[5 + idx]),
            "charges":  charges,
        }
    except (IndexError, ValueError):
        return None


def _flush(name: str, ctype: str, rows: list, customers: list, suppliers: list) -> None:
    if not rows:
        return
    entry = {"name": name, "rows": rows}
    if ctype == "Originated":
        customers.append(entry)
    elif ctype == "Terminated":
        suppliers.append(entry)


# ---------------------------------------------------------------------------
# Type coercion (public — used by feature files)
# ---------------------------------------------------------------------------

def to_int(value) -> int:
    return int(str(value).replace(",", "").strip() or 0)


def to_float(value) -> float:
    return float(str(value).replace(",", ".").strip() or 0)
