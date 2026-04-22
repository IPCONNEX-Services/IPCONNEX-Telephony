import frappe
from frappe.model.document import Document


class DailyGainSummary(Document):
    def before_save(self):
        if not self.partner or not self.partner_type:
            return
        filter_field = "customer" if self.partner_type == "Customer" else "supplier"
        contract = frappe.db.get_value(
            "Telephony Partner Contract",
            {filter_field: self.partner},
            ["company", "sales_manager"],
            as_dict=True,
        )
        if contract:
            self.company = contract.company
            self.sales_manager = contract.sales_manager
