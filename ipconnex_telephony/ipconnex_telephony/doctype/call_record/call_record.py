import frappe
from frappe.model.document import Document


class CallRecord(Document):
    def before_save(self):
        minutes = self.duration_seconds / 60.0
        self.total_cost = round(self.buy_rate * minutes, 6)
        self.total_revenue = round(self.sell_rate * minutes, 6)
        self.margin = round(self.total_revenue - self.total_cost, 6)
