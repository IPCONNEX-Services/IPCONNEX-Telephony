import frappe


def execute(filters=None):
    filters = filters or {}
    group_by = filters.get("group_by") or "Detail"
    columns = _get_columns(group_by)
    data = _get_data(filters, group_by)
    return columns, data


def _get_columns(group_by):
    base = [
        {"label": "Date", "fieldname": "summary_date", "fieldtype": "Date", "width": 110},
    ]

    if group_by == "Customer":
        base += [
            {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
            {"label": "Sales Manager", "fieldname": "sales_manager", "fieldtype": "Link", "options": "Sales Person", "width": 150},
            {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Telephony Company Settings", "width": 150},
        ]
    elif group_by == "Supplier":
        base += [
            {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 180},
        ]
    else:  # Detail
        base += [
            {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 160},
            {"label": "Supplier", "fieldname": "supplier", "fieldtype": "Link", "options": "Supplier", "width": 160},
            {"label": "Sales Manager", "fieldname": "sales_manager", "fieldtype": "Link", "options": "Sales Person", "width": 150},
            {"label": "Company", "fieldname": "company", "fieldtype": "Link", "options": "Telephony Company Settings", "width": 150},
        ]

    base += [
        {"label": "Calls", "fieldname": "total_calls", "fieldtype": "Int", "width": 80},
        {"label": "Minutes", "fieldname": "total_minutes", "fieldtype": "Float", "width": 100},
        {"label": "Cost", "fieldname": "total_cost", "fieldtype": "Currency", "width": 120},
        {"label": "Revenue", "fieldname": "total_revenue", "fieldtype": "Currency", "width": 120},
        {"label": "Margin", "fieldname": "total_margin", "fieldtype": "Currency", "width": 120},
        {"label": "Margin %", "fieldname": "margin_percentage", "fieldtype": "Percent", "width": 100},
    ]
    return base


def _get_data(filters, group_by):
    conditions = []
    values = {}

    if filters.get("from_date"):
        conditions.append("summary_date >= %(from_date)s")
        values["from_date"] = filters["from_date"]

    if filters.get("to_date"):
        conditions.append("summary_date <= %(to_date)s")
        values["to_date"] = filters["to_date"]

    if filters.get("customer"):
        conditions.append("customer = %(customer)s")
        values["customer"] = filters["customer"]

    if filters.get("supplier"):
        conditions.append("supplier = %(supplier)s")
        values["supplier"] = filters["supplier"]

    if filters.get("sales_manager"):
        conditions.append("sales_manager = %(sales_manager)s")
        values["sales_manager"] = filters["sales_manager"]

    if filters.get("company"):
        conditions.append("company = %(company)s")
        values["company"] = filters["company"]

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    if group_by == "Customer":
        return frappe.db.sql(
            f"""
            SELECT
                summary_date,
                customer,
                sales_manager,
                company,
                SUM(total_calls) AS total_calls,
                SUM(total_minutes) AS total_minutes,
                SUM(total_cost) AS total_cost,
                SUM(total_revenue) AS total_revenue,
                SUM(total_margin) AS total_margin,
                ROUND(
                    CASE WHEN SUM(total_revenue) > 0
                    THEN SUM(total_margin) / SUM(total_revenue) * 100
                    ELSE 0 END, 2
                ) AS margin_percentage
            FROM `tabDaily Gain Summary`
            {where}
            GROUP BY summary_date, customer, sales_manager, company
            ORDER BY summary_date DESC, customer
            """,
            values,
            as_dict=True,
        )

    if group_by == "Supplier":
        return frappe.db.sql(
            f"""
            SELECT
                summary_date,
                supplier,
                SUM(total_calls) AS total_calls,
                SUM(total_minutes) AS total_minutes,
                SUM(total_cost) AS total_cost,
                SUM(total_revenue) AS total_revenue,
                SUM(total_margin) AS total_margin,
                ROUND(
                    CASE WHEN SUM(total_revenue) > 0
                    THEN SUM(total_margin) / SUM(total_revenue) * 100
                    ELSE 0 END, 2
                ) AS margin_percentage
            FROM `tabDaily Gain Summary`
            {where}
            GROUP BY summary_date, supplier
            ORDER BY summary_date DESC, supplier
            """,
            values,
            as_dict=True,
        )

    # Detail
    return frappe.db.sql(
        f"""
        SELECT
            summary_date, customer, supplier, sales_manager, company,
            total_calls, total_minutes,
            total_cost, total_revenue, total_margin, margin_percentage
        FROM `tabDaily Gain Summary`
        {where}
        ORDER BY summary_date DESC, customer
        """,
        values,
        as_dict=True,
    )
