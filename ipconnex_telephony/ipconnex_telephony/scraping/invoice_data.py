"""
Invoice data scraper — formats Originated (customer) data as invoice line items.

Each line item represents one country destination billed during the period.

Usage:
    from ipconnex_telephony.scraping.common import IXCClient
    from ipconnex_telephony.scraping.invoice_data import get_invoice_data

    client = IXCClient.connect()
    result = get_invoice_data(client, from_date, to_date)
"""

import json
from datetime import date

from .common import IXCClient


def get_invoice_data(client: IXCClient, from_date: date, to_date: date) -> dict:
    """
    Returns per-customer invoice line items grouped by destination country.

    Shape:
      {
        "from_date": "YYYY-MM-DD",
        "to_date":   "YYYY-MM-DD",
        "invoices": [
          {
            "ixc_name":  str,
            "erp_name":  str,
            "period":    "YYYY-MM-DD / YYYY-MM-DD",
            "total_usd": float,
            "items": [
              {
                "description":  str,    # "Calls to <country> (<N> calls, <M> min)"
                "country":      str,
                "attempts":     int,
                "duration":     float,  # minutes
                "rate_per_min": float,  # charges / duration (0 when duration=0)
                "amount":       float,  # USD
              }
            ]
          }
        ]
      }
    """
    parsed       = client.fetch_traffic(from_date, to_date)
    period_label = f"{from_date.isoformat()} / {to_date.isoformat()}"
    invoices     = []

    for company in parsed["customers"]:
        ixc_name = company["name"]
        items    = [_make_item(r) for r in company["rows"]]
        invoices.append({
            "ixc_name":  ixc_name,
            "erp_name":  client.resolve(ixc_name),
            "period":    period_label,
            "total_usd": round(sum(i["amount"] for i in items), 4),
            "items":     items,
        })

    return {
        "from_date": from_date.isoformat(),
        "to_date":   to_date.isoformat(),
        "invoices":  invoices,
    }


def _make_item(r: dict) -> dict:
    rate = round(r["charges"] / r["duration"], 6) if r["duration"] else 0.0
    return {
        "description":  f"Calls to {r['country']} ({r['attempts']} calls, {r['duration']} min)",
        "country":      r["country"],
        "attempts":     r["attempts"],
        "duration":     r["duration"],
        "rate_per_min": rate,
        "amount":       r["charges"],
    }


if __name__ == "__main__":
    import sys
    from datetime import timedelta

    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)

    client = IXCClient.connect()
    result = get_invoice_data(client, target, target)
    print(json.dumps(result, indent=2))
