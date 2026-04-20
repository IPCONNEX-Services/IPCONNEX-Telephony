"""
Gain stats scraper — fetches Originated (customer) revenue data from IXC.

Returns JSON with charges, minutes, and call attempts per customer × country.

Usage:
    from ipconnex_telephony.scraping.common import IXCClient
    from ipconnex_telephony.scraping.gain_stats import get_gain_stats

    client = IXCClient.connect()
    result = get_gain_stats(client, from_date, to_date)
"""

import json
from datetime import date

from .common import IXCClient


def get_gain_stats(client: IXCClient, from_date: date, to_date: date) -> dict:
    """
    Returns gain stats for all customers in the given date range.

    Shape:
      {
        "from_date": "YYYY-MM-DD",
        "to_date":   "YYYY-MM-DD",
        "customers": [
          {
            "ixc_name":  str,
            "erp_name":  str,
            "totals": {
              "attempts": int,
              "duration": float,   # minutes
              "charges":  float,   # USD
            },
            "by_country": [
              {
                "country":  str,
                "attempts": int,
                "duration": float,
                "asr":      float,  # percent
                "acd":      float,  # seconds
                "charges":  float,
              }
            ]
          }
        ]
      }
    """
    parsed    = client.fetch_traffic(from_date, to_date)
    customers = []

    for company in parsed["customers"]:
        ixc_name = company["name"]
        rows     = company["rows"]
        customers.append({
            "ixc_name": ixc_name,
            "erp_name": client.resolve(ixc_name),
            "totals": {
                "attempts": sum(r["attempts"] for r in rows),
                "duration": round(sum(r["duration"] for r in rows), 4),
                "charges":  round(sum(r["charges"]  for r in rows), 4),
            },
            "by_country": rows,
        })

    return {
        "from_date": from_date.isoformat(),
        "to_date":   to_date.isoformat(),
        "customers": customers,
    }


if __name__ == "__main__":
    import sys
    from datetime import timedelta

    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)

    client = IXCClient.connect()
    result = get_gain_stats(client, target, target)
    print(json.dumps(result, indent=2))
