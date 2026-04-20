import frappe


def execute(filters=None):
    filters = filters or {}
    columns = _get_columns()
    data = _get_data(filters)
    return columns, data


def _get_columns():
    return [
        {"label": "Date", "fieldname": "summary_date", "fieldtype": "Date", "width": 110},
        {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
        {"label": "Destination", "fieldname": "destination_country", "fieldtype": "Data", "width": 130},
        {"label": "Attempts", "fieldname": "total_seizures", "fieldtype": "Int", "width": 90},
        {"label": "Answered", "fieldname": "answered_calls", "fieldtype": "Int", "width": 90},
        {"label": "Failed", "fieldname": "failed_calls", "fieldtype": "Int", "width": 80},
        {"label": "ASR %", "fieldname": "asr", "fieldtype": "Percent", "width": 90},
        {"label": "ASR Status", "fieldname": "asr_status", "fieldtype": "Data", "width": 100},
        {"label": "ACD (s)", "fieldname": "acd_seconds", "fieldtype": "Float", "width": 90},
        {"label": "ACD Status", "fieldname": "acd_status", "fieldtype": "Data", "width": 100},
    ]


def _get_data(filters):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("summary_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("summary_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("supplier"):
        conditions.append("supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]

    if filters.get("customer"):
        conditions.append("customer = %(customer)s")
        values["customer"] = filters["customer"]

    if filters.get("destination_country"):
        conditions.append("destination_country = %(destination_country)s")
        values["destination_country"] = filters["destination_country"]

    if filters.get("asr_status"):
        conditions.append("asr_status = %(asr_status)s")
        values["asr_status"] = filters["asr_status"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    return frappe.db.sql(
        f"""
        SELECT
            summary_date, supplier, customer, destination_country,
            total_seizures, answered_calls, failed_calls,
            asr, asr_status, acd_seconds, acd_status
        FROM `tabCall Quality Summary`
        {where}
        ORDER BY summary_date DESC, asr ASC
        """,
        values,
        as_dict=True,
    )
