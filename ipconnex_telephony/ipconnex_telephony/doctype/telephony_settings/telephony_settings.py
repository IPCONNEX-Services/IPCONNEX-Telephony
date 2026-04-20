import frappe
from frappe.model.document import Document


class TelephonySettings(Document):
    def validate(self):
        if self.sync_interval_minutes < 5:
            frappe.throw("Sync interval must be at least 5 minutes.")
