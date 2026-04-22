import frappe
from frappe.model.document import Document


class CallQualitySummary(Document):
    def before_save(self):
        self.failed_calls = self.total_seizures - self.answered_calls
        self.asr = round(self.answered_calls / self.total_seizures * 100, 2) if self.total_seizures else 0
        self.acd_seconds = round(self.total_duration_seconds / self.answered_calls, 2) if self.answered_calls else 0
        self.asr_status = _status(self.asr, self.asr_target, higher_is_better=True)
        self.acd_status = _status(self.acd_seconds, self.acd_target_seconds, higher_is_better=True)


def _status(value, target, higher_is_better=True):
    if not target:
        return ""
    ratio = value / target
    if higher_is_better:
        if ratio >= 1.0:
            return "OK"
        if ratio >= 0.8:
            return "Warning"
        return "Critical"
    else:
        if ratio <= 1.0:
            return "OK"
        if ratio <= 1.2:
            return "Warning"
        return "Critical"
