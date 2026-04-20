import frappe
from frappe.model.document import Document


class TelephonyTicket(Document):
    def before_insert(self):
        if self.telephony_contract and not self.customer:
            self.customer = frappe.db.get_value(
                "Telephony Contract", self.telephony_contract, "customer"
            )
