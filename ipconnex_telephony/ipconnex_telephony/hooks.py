app_name = "ipconnex_telephony"
app_title = "Ipconnex Telephony"
app_publisher = "IPCONNEX"
app_description = "SIP/VoIP billing — ACR scraping, auto-invoicing, gain dashboards"
app_email = "yacine.g@ipconnex.com"
app_license = "MIT"

# Fixtures — Dashboard, Charts, Number Cards
fixtures = [
    {"dt": "Number Card", "filters": [["module", "=", "Ipconnex Telephony"]]},
    {"dt": "Dashboard Chart", "filters": [["module", "=", "Ipconnex Telephony"]]},
    {"dt": "Dashboard", "filters": [["module", "=", "Ipconnex Telephony"]]},
]

# Scheduled Tasks
scheduler_events = {
    "daily": [
        "ipconnex_telephony.utils.acr_scraper.sync_call_records",
        "ipconnex_telephony.utils.gain_aggregator.build_daily_gain_summaries",
        "ipconnex_telephony.utils.quality_aggregator.build_daily_quality_summaries",
        "ipconnex_telephony.utils.invoice_generator.run_billing_cycle",
        "ipconnex_telephony.utils.invoice_generator.retry_failed_invoices",
    ],
}

# DocType overrides
# override_doctype_class = {}

# DocEvents
# doc_events = {}
