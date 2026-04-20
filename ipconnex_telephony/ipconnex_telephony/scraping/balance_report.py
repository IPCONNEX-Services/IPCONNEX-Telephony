"""
Balance report scraper — fetches account balances from IXC /system_reports/balance_report.

Usage:
    from scraping.common import IXCClient
    from scraping.balance_report import get_balance_report

    client = IXCClient.connect(username, password)
    result = get_balance_report(client)
"""

import json
import re
from datetime import date

from bs4 import BeautifulSoup

from .common import IXCClient, TABLE_REGEX, to_float


def get_balance_report(client: IXCClient) -> dict:
    """
    Returns current account balances from the IXC balance report.

    Shape:
      {
        "fetched_at": "YYYY-MM-DD",
        "accounts": [
          {
            "ixc_name": str,
            "erp_name": str,
            "balance":  float,   # USD (negative = owing)
            "currency": str,
          }
        ]
      }
    """
    html     = client.fetch_balance_html()
    accounts = _parse_balance(html, client)

    return {
        "fetched_at": date.today().isoformat(),
        "accounts":   accounts,
    }


def _parse_balance(html: str, client: IXCClient) -> list:
    tables = re.findall(TABLE_REGEX, html, re.IGNORECASE | re.DOTALL)
    if not tables:
        raise ValueError("No class='table' element found in balance report HTML")

    cleaned  = re.sub(r'[^a-zA-Z0-9"<>/ \-!.,]', '', tables[0])
    soup     = BeautifulSoup(cleaned, "html5lib")
    accounts = []

    for tr in soup.find_all("tr"):
        cells = [td.text.strip() for td in tr.find_all("td")]
        if len(cells) < 2 or not cells[0]:
            continue
        ixc_name = cells[0]
        accounts.append({
            "ixc_name": ixc_name,
            "erp_name": client.resolve(ixc_name),
            "balance":  to_float(cells[1]),
            "currency": cells[2].strip() if len(cells) > 2 else "USD",
        })

    return accounts


if __name__ == "__main__":
    import sys

    username = sys.argv[1]
    password = sys.argv[2]

    client = IXCClient.connect(username, password)
    result = get_balance_report(client)
    print(json.dumps(result, indent=2))
