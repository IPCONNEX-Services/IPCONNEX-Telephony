import frappe
from frappe.model.document import Document


class InvoiceGenerationLog(Document):
    @frappe.whitelist()
    def retry(self):
        """Retry this failed log entry from the form button."""
        from ipconnex_telephony.utils.invoice_generator import retry_log_entry
        retry_log_entry(self.name)
