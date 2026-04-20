"""
ASR quality scraper — fetches Terminated (supplier) ASR/ACD data from IXC.

IXC already provides ASR% and ACD(s) per row — no recomputation needed.
Answered calls are derived as: round(attempts × asr / 100).

Usage:
    from ipconnex_telephony.scraping.common import IXCClient
    from ipconnex_telephony.scraping.asr_quality import get_asr_quality

    client = IXCClient.connect()
    result = get_asr_quality(client, from_date, to_date)
"""

import json
from datetime import date

from .common import IXCClient

ASR_CRITICAL = 30.0   # % — below this: critical
ASR_WARNING  = 60.0   # % — below this: warning
ACD_LOW      = 30.0   # seconds — below this: low


def get_asr_quality(client: IXCClient, from_date: date, to_date: date) -> dict:
    """
    Returns ASR/ACD quality stats for all suppliers in the given date range.

    Shape:
      {
        "from_date": "YYYY-MM-DD",
        "to_date":   "YYYY-MM-DD",
        "suppliers": [
          {
            "ixc_name": str,
            "erp_name": str,
            "totals": {
              "attempts":    int,
              "answered":    int,
              "asr":         float,   # percent  (weighted from totals)
              "duration_s":  int,     # total seconds
              "acd":         float,   # seconds  (duration_s / answered)
            },
            "by_country": [
              {
                "country":    str,
                "attempts":   int,
                "answered":   int,
                "duration_s": int,
                "asr":        float,
                "asr_status": str,    # "ok" | "warning" | "critical"
                "acd":        float,  # IXC-provided, not recomputed
                "acd_status": str,    # "ok" | "low"
                "charges":    float,
              }
            ]
          }
        ]
      }
    """
    parsed    = client.fetch_traffic(from_date, to_date)
    suppliers = []

    for company in parsed["suppliers"]:
        ixc_name     = company["name"]
        enriched     = [_enrich_row(r) for r in company["rows"]]

        total_att    = sum(r["attempts"]   for r in enriched)
        total_ans    = sum(r["answered"]   for r in enriched)
        total_dur_s  = sum(r["duration_s"] for r in enriched)
        total_asr    = round(total_ans / total_att * 100, 2) if total_att else 0.0
        total_acd    = round(total_dur_s / total_ans, 2)     if total_ans else 0.0

        suppliers.append({
            "ixc_name": ixc_name,
            "erp_name": client.resolve(ixc_name),
            "totals": {
                "attempts":   total_att,
                "answered":   total_ans,
                "asr":        total_asr,
                "duration_s": total_dur_s,
                "acd":        total_acd,
            },
            "by_country": enriched,
        })

    return {
        "from_date": from_date.isoformat(),
        "to_date":   to_date.isoformat(),
        "suppliers": suppliers,
    }


def _enrich_row(r: dict) -> dict:
    answered   = round(r["attempts"] * r["asr"] / 100) if r["asr"] else 0
    duration_s = int(r["duration"] * 60)
    return {
        "country":    r["country"],
        "attempts":   r["attempts"],
        "answered":   answered,
        "duration_s": duration_s,
        "asr":        r["asr"],
        "asr_status": _asr_status(r["asr"]),
        "acd":        r["acd"],          # IXC-provided — no recomputation
        "acd_status": "low" if r["acd"] < ACD_LOW else "ok",
        "charges":    r["charges"],
    }


def _asr_status(asr: float) -> str:
    if asr < ASR_CRITICAL:
        return "critical"
    if asr < ASR_WARNING:
        return "warning"
    return "ok"


if __name__ == "__main__":
    import sys
    from datetime import timedelta

    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else date.today() - timedelta(days=1)

    client = IXCClient.connect()
    result = get_asr_quality(client, target, target)
    print(json.dumps(result, indent=2))
