import frappe
from frappe.utils import now_datetime


def build_daily_quality_summaries():
    """
    Incremental — re-aggregates only dates that have Call Records
    created after the last quality sync timestamp.
    """
    settings = frappe.get_single("Telephony Settings")
    since = settings.last_quality_sync

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
        frappe.logger().info("Quality aggregator: no new records, skipping.")
        return

    for date in affected_dates:
        _aggregate_date(date)

    frappe.db.set_value("Telephony Settings", "Telephony Settings", "last_quality_sync", now_datetime())
    frappe.db.commit()
    frappe.logger().info(f"Call Quality Summary: updated {len(affected_dates)} date(s)")


def _aggregate_date(target_date):
    rows = frappe.db.sql(
        """
        SELECT
            customer,
            supplier,
            destination_country,
            COUNT(*) AS total_seizures,
            SUM(CASE WHEN duration_seconds > 0 THEN 1 ELSE 0 END) AS answered_calls,
            SUM(CASE WHEN duration_seconds > 0 THEN duration_seconds ELSE 0 END) AS total_duration_seconds
        FROM `tabCall Record`
        WHERE call_date = %s AND is_excluded = 0
        GROUP BY customer, supplier, destination_country
        """,
        target_date,
        as_dict=True,
    )

    for row in rows:
        values = {
            "total_seizures": row.total_seizures,
            "answered_calls": row.answered_calls,
            "total_duration_seconds": row.total_duration_seconds,
        }

        existing = frappe.db.get_value(
            "Call Quality Summary",
            {
                "summary_date": target_date,
                "customer": row.customer,
                "supplier": row.supplier,
                "destination_country": row.destination_country or "",
                "period": "Daily",
            },
            "name",
        )
        if existing:
            doc = frappe.get_doc("Call Quality Summary", existing)
            doc.update(values)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({
                "doctype": "Call Quality Summary",
                "summary_date": target_date,
                "period": "Daily",
                "customer": row.customer,
                "supplier": row.supplier,
                "destination_country": row.destination_country or "",
                **values,
            }).insert(ignore_permissions=True)
