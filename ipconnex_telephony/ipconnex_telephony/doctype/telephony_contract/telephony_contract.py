import frappe
from frappe.model.document import Document
from frappe.utils import today, add_days, getdate


class TelephonyContract(Document):
    def validate(self):
        if not self.customer and not self.supplier:
            frappe.throw("Set at least one of Customer or Supplier on the contract.")

    def get_current_period(self, as_of=None):
        """Return (period_start, period_end) for the billing period containing `as_of`."""
        as_of = getdate(as_of or today())
        start = getdate(self.start_date)

        if self.billing_cycle == "Weekly":
            return _weekly_period(start, as_of)
        elif self.billing_cycle == "Fortnightly":
            return _fortnightly_period(as_of)
        else:
            return _monthly_period(as_of)


def _weekly_period(contract_start, as_of):
    delta = (as_of - contract_start).days
    week_number = delta // 7
    period_start = add_days(contract_start, week_number * 7)
    period_end = add_days(period_start, 6)
    return period_start, period_end


def _fortnightly_period(as_of):
    if as_of.day < 16:
        period_start = as_of.replace(day=1)
        period_end = as_of.replace(day=15)
    else:
        import calendar
        period_start = as_of.replace(day=16)
        last_day = calendar.monthrange(as_of.year, as_of.month)[1]
        period_end = as_of.replace(day=last_day)
    return period_start, period_end


def _monthly_period(as_of):
    import calendar
    period_start = as_of.replace(day=1)
    last_day = calendar.monthrange(as_of.year, as_of.month)[1]
    period_end = as_of.replace(day=last_day)
    return period_start, period_end
