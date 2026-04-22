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
from datetime import date, datetime, timezone

from .common import IXCClient


def _get_thresholds():
    try:
        import frappe
        s = frappe.get_single("Telephony Settings")
        return (s.asr_critical or 30.0), (s.asr_warning or 50.0), (s.acd_low or 30.0)
    except Exception:
        return 30.0, 50.0, 30.0


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
    asr_critical, asr_warning, acd_low = _get_thresholds()
    parsed    = client.fetch_traffic(from_date, to_date)
    suppliers = []

    for company in parsed["suppliers"]:
        ixc_name     = company["name"]
        enriched     = [_enrich_row(r, asr_critical, asr_warning, acd_low) for r in company["rows"]]

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


def _enrich_row(r: dict, asr_critical: float, asr_warning: float, acd_low: float) -> dict:
    answered   = round(r["attempts"] * r["asr"] / 100) if r["asr"] else 0
    duration_s = int(r["duration"] * 60)
    return {
        "country":    r["country"],
        "attempts":   r["attempts"],
        "answered":   answered,
        "duration_s": duration_s,
        "asr":        r["asr"],
        "asr_status": "critical" if r["asr"] < asr_critical else ("warning" if r["asr"] < asr_warning else "ok"),
        "acd":        r["acd"],
        "acd_status": "low" if r["acd"] < acd_low else "ok",
        "charges":    r["charges"],
    }


if __name__ == "__main__":
    import sys
    from datetime import timedelta

    target = date.fromisoformat(sys.argv[1]) if len(sys.argv) > 1 else datetime.now(timezone.utc).date() - timedelta(days=1)

    client = IXCClient.connect()
    result = get_asr_quality(client, target, target)
    print(json.dumps(result, indent=2))
