app_name = "ipconnex_telephony"
app_title = "IPCONNEX Telephony"
app_publisher = "IPCONNEX"
app_description = "SIP/VoIP billing — ACR scraping, auto-invoicing, gain dashboards"
app_email = "yacine.g@ipconnex.com"
app_license = "MIT"

# Fixtures — Dashboard, Charts, Number Cards
fixtures = [
    {"dt": "Number Card", "filters": [["module", "=", "IPCONNEX Telephony"]]},
    {"dt": "Dashboard Chart", "filters": [["module", "=", "IPCONNEX Telephony"]]},
    {"dt": "Dashboard", "filters": [["module", "=", "IPCONNEX Telephony"]]},
]

# Scheduled Tasks
scheduler_events = {
    "all": [
        "ipconnex_telephony.utils.ixc_scraper.sync_ixc_stats",
    ],
    "daily": [
        "ipconnex_telephony.utils.invoice_generator.run_billing_cycle",
        "ipconnex_telephony.utils.invoice_generator.retry_failed_invoices",
    ],
}

# DocType overrides
# override_doctype_class = {}

# DocEvents
# doc_events = {}
