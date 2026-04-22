import frappe
from frappe.utils import now_datetime


def build_daily_gain_summaries():
    """
    Incremental — re-aggregates only dates that have Call Records
    created after the last gain sync timestamp.
    """
    settings = frappe.get_single("Telephony Settings")
    since = settings.last_gain_sync

    filters = {"is_excluded": 0}
    if since:
        filters["creation"] = (">", since)

    affected_dates = frappe.db.get_all(
        "Call Record",
        filters=filters,
        fields=["call_date"],
        distinct=True,
        pluck="call_date",
    )

    if not affected_dates:
        frappe.logger().info("Gain aggregator: no new records, skipping.")
        return

    for date in affected_dates:
        _aggregate_date(date)

    frappe.db.set_value("Telephony Settings", "Telephony Settings", "last_gain_sync", now_datetime())
    frappe.db.commit()
    frappe.logger().info(f"Daily Gain Summary: updated {len(affected_dates)} date(s)")


def _aggregate_date(target_date):
    rows = frappe.db.sql(
        """
        SELECT
            customer,
            supplier,
            COUNT(*) AS total_calls,
            SUM(duration_seconds) / 60.0 AS total_minutes,
            SUM(total_cost) AS total_cost,
            SUM(total_revenue) AS total_revenue,
            SUM(margin) AS total_margin
        FROM `tabCall Record`
        WHERE call_date = %s AND is_excluded = 0
        GROUP BY customer, supplier
        """,
        target_date,
        as_dict=True,
    )

    for row in rows:
        margin_pct = (row.total_margin / row.total_revenue * 100) if row.total_revenue else 0
        contract_info = _get_contract_info(row.customer)
        values = {
            "total_calls": row.total_calls,
            "total_minutes": round(row.total_minutes, 2),
            "total_cost": row.total_cost,
            "total_revenue": row.total_revenue,
            "total_margin": row.total_margin,
            "margin_percentage": round(margin_pct, 2),
            "sales_manager": contract_info.get("sales_manager") or None,
            "company": contract_info.get("company") or None,
        }

        existing = frappe.db.get_value(
            "Daily Gain Summary",
            {"summary_date": target_date, "customer": row.customer, "supplier": row.supplier},
            "name",
        )
        if existing:
            frappe.db.set_value("Daily Gain Summary", existing, values)
        else:
            frappe.get_doc({
                "doctype": "Daily Gain Summary",
                "summary_date": target_date,
                "customer": row.customer,
                "supplier": row.supplier,
                **values,
            }).insert(ignore_permissions=True)


def _get_contract_info(customer):
    result = frappe.db.get_value(
        "Telephony Partner Contract",
        {"customer": customer, "is_active": 1},
        ["sales_manager", "company"],
        as_dict=True,
    )
    return result or {}
