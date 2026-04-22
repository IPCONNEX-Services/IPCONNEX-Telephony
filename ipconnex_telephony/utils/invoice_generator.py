"""
Invoice generator — runs daily, emits up to two invoices per contract per period:

  Customer leg -> Sales Invoice     (sums total_revenue on Call Records)
  Supplier leg -> Purchase Invoice  (sums total_cost on Call Records)

An interconnect contract (same partner as both customer and supplier) produces
both legs independently in the same run — a failure on one leg does not block
the other. Each leg gets its own Invoice Generation Log row keyed by direction.
"""

import traceback
import frappe
from frappe.utils import getdate, add_days, now_datetime
import calendar

from ipconnex_telephony.utils import utc_today, utc_now


CUSTOMER_LEG = "Customer"
SUPPLIER_LEG = "Supplier"


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------

def run_billing_cycle(as_of=None):
    as_of = getdate(as_of) if as_of else utc_today()
    period_end = add_days(as_of, -1)  # yesterday — all data for that day is already synced
    contracts = frappe.get_all(
        "Telephony Partner Contract",
        filters={"is_active": 1},
        fields=["name", "customer", "supplier", "billing_cycle", "start_date", "currency", "company"],
    )
    for contract in contracts:
        if not _is_period_end(contract, period_end):
            continue
        if contract.get("customer"):
            _process(contract, period_end, CUSTOMER_LEG)
        if contract.get("supplier"):
            _process(contract, period_end, SUPPLIER_LEG)


# ---------------------------------------------------------------------------
# Manual trigger API — callable from button or script
# ---------------------------------------------------------------------------

@frappe.whitelist()
def generate_invoice_now(contract_name, direction, period_end=None):
    """
    Manually generate a Sales Invoice (direction='Customer') or Purchase Invoice
    (direction='Supplier') for a contract, without waiting for the billing cycle.

    period_end defaults to yesterday. Raises if a successful invoice already exists
    for that period.
    """
    contract = frappe.get_doc("Telephony Partner Contract", contract_name)
    if not contract.is_active:
        frappe.throw(f"Contract {contract_name} is not active")

    period_end_date = getdate(period_end) if period_end else add_days(utc_today(), -1)

    if direction == CUSTOMER_LEG and not contract.customer:
        frappe.throw(f"Contract {contract_name} has no customer")
    if direction == SUPPLIER_LEG and not contract.supplier:
        frappe.throw(f"Contract {contract_name} has no supplier")

    _process(contract.as_dict(), period_end_date, direction)
    log = frappe.db.get_value(
        "Invoice Generation Log",
        {"contract": contract_name, "period_end": period_end_date, "direction": direction},
        ["status", "sales_invoice", "purchase_invoice", "error_message", "total_amount"],
        as_dict=True,
    )
    if log and log.status == "Failed":
        frappe.throw(log.error_message or "Invoice generation failed")
    invoice_name = log.sales_invoice if direction == CUSTOMER_LEG else log.purchase_invoice
    return {"invoice": invoice_name, "amount": log.total_amount if log else None}


# ---------------------------------------------------------------------------
# Retry API — called from scheduler or form button
# ---------------------------------------------------------------------------

@frappe.whitelist()
def retry_failed_invoices():
    """Retry all logs with status = Failed."""
    failed = frappe.get_all(
        "Invoice Generation Log",
        filters={"status": "Failed"},
        fields=["name"],
        pluck="name",
    )
    for log_name in failed:
        retry_log_entry(log_name)
    return {"retried": len(failed)}


def retry_log_entry(log_name):
    log = frappe.get_doc("Invoice Generation Log", log_name)
    contract = frappe.get_doc("Telephony Partner Contract", log.contract)
    _attempt(contract.as_dict(), log.period_end, log.direction, existing_log=log)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _process(contract, period_end, direction):
    if frappe.db.exists(
        "Invoice Generation Log",
        {"contract": contract["name"], "period_end": period_end, "direction": direction, "status": "Success"},
    ):
        return

    existing_log_name = frappe.db.get_value(
        "Invoice Generation Log",
        {
            "contract": contract["name"],
            "period_end": period_end,
            "direction": direction,
            "status": ("in", ["Pending", "Failed"]),
        },
        "name",
    )
    log = frappe.get_doc("Invoice Generation Log", existing_log_name) if existing_log_name else None
    _attempt(contract, period_end, direction, existing_log=log)


def _attempt(contract, period_end, direction, existing_log=None):
    period_end = getdate(period_end)
    period_start = _get_period_start(contract, period_end)

    log = existing_log or frappe.get_doc({
        "doctype": "Invoice Generation Log",
        "direction": direction,
        "customer": contract.get("customer"),
        "supplier": contract.get("supplier"),
        "contract": contract["name"],
        "period_start": period_start,
        "period_end": period_end,
        "status": "Pending",
    })

    if not existing_log:
        log.insert(ignore_permissions=True)

    log.last_attempt = utc_now()
    log.retry_count = (log.retry_count or 0) + (1 if existing_log else 0)

    try:
        if direction == CUSTOMER_LEG:
            invoice_name, call_count, total_amount = _generate_sales_invoice(contract, period_start, period_end)
            log.sales_invoice = invoice_name
        else:
            invoice_name, call_count, total_amount = _generate_purchase_invoice(contract, period_start, period_end)
            log.purchase_invoice = invoice_name

        log.status = "Success"
        log.summary_count = call_count
        log.total_amount = total_amount
        log.error_message = None
    except Exception:
        log.status = "Failed"
        log.error_message = traceback.format_exc()
        frappe.logger().error(
            f"Invoice generation failed ({direction}) for contract {contract['name']} "
            f"({period_start} → {period_end}):\n{log.error_message}"
        )

    log.save(ignore_permissions=True)
    frappe.db.commit()


# ---------------------------------------------------------------------------
# Customer leg — Sales Invoice
# ---------------------------------------------------------------------------

def _generate_sales_invoice(contract, period_start, period_end):
    summaries = frappe.get_all(
        "Daily Gain Summary",
        filters={
            "customer": contract["customer"],
            "summary_date": ("between", [period_start, period_end]),
            "customer_invoice_status": "Pending",
        },
        fields=["name", "total_revenue", "total_minutes"],
    )

    if not summaries:
        frappe.throw(f"No pending gain summaries for {contract['customer']} ({period_start} → {period_end})")

    tcs = _get_company_settings(contract.get("company"))
    item_code = _get_or_create_telephony_item()

    items = _build_route_items(
        party=contract["customer"],
        rate_field="sell_rate",
        party_filter="customer",
        period_start=period_start,
        period_end=period_end,
        item_code=item_code,
        account_field="income_account",
        account_value=tcs.income_account if tcs else None,
        cost_center=tcs.cost_center if tcs else None,
        fallback_minutes=sum(r["total_minutes"] for r in summaries),
        fallback_amount=sum(r["total_revenue"] for r in summaries),
    )

    total_amount = sum(i["amount"] for i in items)

    invoice_data = {
        "doctype": "Sales Invoice",
        "customer": contract["customer"],
        "currency": contract["currency"],
        "posting_date": str(period_end),
        "due_date": str(add_days(period_end, 30)),
        "items": items,
    }

    if tcs:
        if tcs.company:
            invoice_data["company"] = tcs.company
        if tcs.receivable_account:
            invoice_data["debit_to"] = tcs.receivable_account
        if tcs.taxes_and_charges:
            invoice_data["taxes_and_charges"] = tcs.taxes_and_charges
        if tcs.terms_and_conditions:
            invoice_data["tc_name"] = tcs.terms_and_conditions
        if tcs.company_address:
            invoice_data["company_address"] = tcs.company_address

    invoice = frappe.get_doc(invoice_data)
    invoice.insert(ignore_permissions=True)
    invoice.submit()

    _mark_summaries_invoiced(
        [r["name"] for r in summaries],
        status_field="customer_invoice_status",
        invoice_field="sales_invoice",
        invoice_name=invoice.name,
    )

    return invoice.name, len(summaries), total_amount


# ---------------------------------------------------------------------------
# Supplier leg — Purchase Invoice
# ---------------------------------------------------------------------------

def _generate_purchase_invoice(contract, period_start, period_end):
    summaries = frappe.get_all(
        "Daily Gain Summary",
        filters={
            "supplier": contract["supplier"],
            "summary_date": ("between", [period_start, period_end]),
            "supplier_invoice_status": "Pending",
        },
        fields=["name", "total_cost", "total_minutes"],
    )

    if not summaries:
        frappe.throw(f"No pending gain summaries for {contract['supplier']} ({period_start} → {period_end})")

    tcs = _get_company_settings(contract.get("company"))
    item_code = _get_or_create_telephony_item()

    items = _build_route_items(
        party=contract["supplier"],
        rate_field="buy_rate",
        party_filter="supplier",
        period_start=period_start,
        period_end=period_end,
        item_code=item_code,
        account_field="expense_account",
        account_value=tcs.expense_account if tcs else None,
        cost_center=tcs.cost_center if tcs else None,
        fallback_minutes=sum(r["total_minutes"] for r in summaries),
        fallback_amount=sum(r["total_cost"] for r in summaries),
    )

    total_amount = sum(i["amount"] for i in items)

    invoice_data = {
        "doctype": "Purchase Invoice",
        "supplier": contract["supplier"],
        "currency": contract["currency"],
        "posting_date": str(period_end),
        "due_date": str(add_days(period_end, 30)),
        "items": items,
    }

    if tcs:
        if tcs.company:
            invoice_data["company"] = tcs.company
        if tcs.payable_account:
            invoice_data["credit_to"] = tcs.payable_account

    invoice = frappe.get_doc(invoice_data)
    invoice.insert(ignore_permissions=True)
    invoice.submit()

    _mark_summaries_invoiced(
        [r["name"] for r in summaries],
        status_field="supplier_invoice_status",
        invoice_field="purchase_invoice",
        invoice_name=invoice.name,
    )

    return invoice.name, len(summaries), total_amount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_route_items(party, rate_field, party_filter, period_start, period_end,
                        item_code, account_field, account_value, cost_center,
                        fallback_minutes, fallback_amount):
    """
    Returns a list of invoice item dicts — one per destination_country + rate.
    qty = minutes, rate = per-minute price.
    Falls back to a single summary item when no Call Records exist.
    """
    routes = frappe.db.sql(
        f"""
        SELECT
            destination_country,
            {rate_field}                            AS rate,
            ROUND(SUM(duration_seconds) / 60.0, 6) AS minutes
        FROM `tabCall Record`
        WHERE {party_filter} = %s
          AND DATE(call_date) BETWEEN %s AND %s
          AND is_excluded = 0
        GROUP BY destination_country, {rate_field}
        ORDER BY minutes DESC
        """,
        [party, period_start, period_end],
        as_dict=True,
    )

    def _make_item(description, qty, rate):
        item = {
            "item_code": item_code,
            "description": description,
            "qty": round(qty, 6),
            "rate": round(rate, 6),
            "amount": round(qty * rate, 6),
        }
        if account_value:
            item[account_field] = account_value
        if cost_center:
            item["cost_center"] = cost_center
        return item

    if not routes:
        return [_make_item(
            f"Telephony services {period_start} to {period_end} ({round(fallback_minutes, 2)} min)",
            qty=1,
            rate=fallback_amount,
        )]

    return [
        _make_item(
            description=(
                f"{r.destination_country or 'Unknown'} | "
                f"{round(r.minutes, 2)} min | "
                f"rate: {round(r.rate or 0, 6)} | "
                f"amount: {round(r.minutes * (r.rate or 0), 4)}"
            ),
            qty=r.minutes,
            rate=r.rate or 0,
        )
        for r in routes
    ]


def _mark_summaries_invoiced(summary_names, status_field, invoice_field, invoice_name):
    placeholders = ", ".join(["%s"] * len(summary_names))
    frappe.db.sql(
        f"""UPDATE `tabDaily Gain Summary`
            SET {status_field} = 'Invoiced', {invoice_field} = %s, modified = NOW()
            WHERE name IN ({placeholders})""",
        [invoice_name] + summary_names,
    )


def _is_period_end(contract, d):
    """Returns True if `d` is the last day of a billing period for the contract."""
    cycle = contract["billing_cycle"]
    if cycle == "Monthly":
        return d.day == calendar.monthrange(d.year, d.month)[1]
    if cycle == "Fortnightly":
        last_day = calendar.monthrange(d.year, d.month)[1]
        return d.day in (15, last_day)
    if cycle == "Weekly":
        start = getdate(contract["start_date"])
        if d < start:
            return False
        return ((d - start).days + 1) % 7 == 0
    return False


def _get_period_start(contract, period_end):
    cycle = contract["billing_cycle"]
    if cycle == "Monthly":
        return period_end.replace(day=1)
    if cycle == "Fortnightly":
        return period_end.replace(day=16) if period_end.day > 15 else period_end.replace(day=1)
    return add_days(period_end, -6)


def _get_company_settings(company_name):
    if not company_name:
        return None
    if not frappe.db.exists("Telephony Company Settings", company_name):
        return None
    return frappe.get_doc("Telephony Company Settings", company_name)


def _get_or_create_telephony_item():
    item_code = "TELEPHONY-SVC"
    if not frappe.db.exists("Item", item_code):
        frappe.get_doc({
            "doctype": "Item",
            "item_code": item_code,
            "item_name": "Telephony Services",
            "item_group": "Services",
            "is_stock_item": 0,
            "is_sales_item": 1,
            "is_purchase_item": 1,
            "stock_uom": "Nos",
        }).insert(ignore_permissions=True)
    return item_code
