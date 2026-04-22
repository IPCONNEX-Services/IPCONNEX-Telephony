from datetime import datetime, timezone


def utc_today():
    """Current date in UTC — use everywhere instead of frappe.utils.today() or date.today()."""
    return datetime.now(timezone.utc).date()


def utc_now():
    """Current datetime in UTC — use for timestamp comparisons."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
