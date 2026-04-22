import frappe
from frappe.model.document import Document


class RateTask(Document):
    def before_insert(self):
        if self.telephony_contract and not self.customer:
            self.customer = frappe.db.get_value(
                "Telephony Partner Contract", self.telephony_contract, "customer"
            )
        if self.telephony_contract and not self.sales_manager:
            self.sales_manager = frappe.db.get_value(
                "Telephony Partner Contract", self.telephony_contract, "sales_manager"
            )
