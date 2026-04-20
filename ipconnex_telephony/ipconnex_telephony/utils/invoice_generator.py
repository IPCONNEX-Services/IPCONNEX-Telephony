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
from frappe.utils import today, getdate, add_days, now_datetime
import calendar


CUSTOMER_LEG = "Customer"
SUPPLIER_LEG = "Supplier"


# ---------------------------------------------------------------------------
# Scheduled entry point
# ---------------------------------------------------------------------------

def run_billing_cycle(as_of=None):
    as_of = getdate(as_of or today())
    contracts = frappe.get_all(
        "Telephony Contract",
        filters={"is_active": 1},
        fields=["name", "customer", "supplier", "billing_cycle", "start_date", "currency", "company"],
    )
    for contract in contracts:
        if not _period_ends_today(contract, as_of):
            continue
        if contract.get("customer"):
            _process(contract, as_of, CUSTOMER_LEG)
        if contract.get("supplier"):
            _process(contract, as_of, SUPPLIER_LEG)


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
    contract = frappe.get_doc("Telephony Contract", log.contract)
    _attempt(contract.as_dict(), log.period_end, log.direction, existing_log=log)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def _process(contract, period_end, direction):
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

    log.last_attempt = now_datetime()
    log.retry_count = (log.retry_count or 0) + (1 if existing_log else 0)

    try:
        if direction == CUSTOMER_LEG:
            invoice_name, call_count, total_amount = _generate_sales_invoice(contract, period_start, period_end)
            log.sales_invoice = invoice_name
        else:
            invoice_name, call_count, total_amount = _generate_purchase_invoice(contract, period_start, period_end)
            log.purchase_invoice = invoice_name

        log.status = "Success"
        log.call_count = call_count
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
    pending_calls = frappe.get_all(
        "Call Record",
        filters={
            "customer": contract["customer"],
            "call_date": ("between", [period_start, period_end]),
            "customer_invoice_status": "Pending",
            "is_excluded": 0,
        },
        fields=["name", "total_revenue", "duration_seconds"],
    )

    if not pending_calls:
        frappe.throw(f"No pending customer-side calls for {contract['customer']} ({period_start} → {period_end})")

    total_amount = sum(c["total_revenue"] for c in pending_calls)
    total_minutes = sum(c["duration_seconds"] for c in pending_calls) / 60.0

    tcs = _get_company_settings(contract.get("company"))
    item_code = _get_or_create_telephony_item()

    item = {
        "item_code": item_code,
        "description": (
            f"Telephony services {period_start} to {period_end} "
            f"({len(pending_calls)} calls, {round(total_minutes, 2)} min)"
        ),
        "qty": 1,
        "rate": total_amount,
        "amount": total_amount,
    }
    if tcs and tcs.income_account:
        item["income_account"] = tcs.income_account
    if tcs and tcs.cost_center:
        item["cost_center"] = tcs.cost_center

    invoice_data = {
        "doctype": "Sales Invoice",
        "customer": contract["customer"],
        "currency": contract["currency"],
        "posting_date": str(period_end),
        "due_date": str(add_days(period_end, 30)),
        "items": [item],
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

    _mark_calls_invoiced(
        [c["name"] for c in pending_calls],
        status_field="customer_invoice_status",
        invoice_field="sales_invoice",
        invoice_name=invoice.name,
    )

    return invoice.name, len(pending_calls), total_amount


# ---------------------------------------------------------------------------
# Supplier leg — Purchase Invoice
# ---------------------------------------------------------------------------

def _generate_purchase_invoice(contract, period_start, period_end):
    pending_calls = frappe.get_all(
        "Call Record",
        filters={
            "supplier": contract["supplier"],
            "call_date": ("between", [period_start, period_end]),
            "supplier_invoice_status": "Pending",
            "is_excluded": 0,
        },
        fields=["name", "total_cost", "duration_seconds"],
    )

    if not pending_calls:
        frappe.throw(f"No pending supplier-side calls for {contract['supplier']} ({period_start} → {period_end})")

    total_amount = sum(c["total_cost"] for c in pending_calls)
    total_minutes = sum(c["duration_seconds"] for c in pending_calls) / 60.0

    tcs = _get_company_settings(contract.get("company"))
    item_code = _get_or_create_telephony_item()

    item = {
        "item_code": item_code,
        "description": (
            f"Telephony services {period_start} to {period_end} "
            f"({len(pending_calls)} calls, {round(total_minutes, 2)} min)"
        ),
        "qty": 1,
        "rate": total_amount,
        "amount": total_amount,
    }
    if tcs and tcs.expense_account:
        item["expense_account"] = tcs.expense_account
    if tcs and tcs.cost_center:
        item["cost_center"] = tcs.cost_center

    invoice_data = {
        "doctype": "Purchase Invoice",
        "supplier": contract["supplier"],
        "currency": contract["currency"],
        "posting_date": str(period_end),
        "due_date": str(add_days(period_end, 30)),
        "items": [item],
    }

    if tcs:
        if tcs.company:
            invoice_data["company"] = tcs.company
        if tcs.payable_account:
            invoice_data["credit_to"] = tcs.payable_account

    invoice = frappe.get_doc(invoice_data)
    invoice.insert(ignore_permissions=True)
    invoice.submit()

    _mark_calls_invoiced(
        [c["name"] for c in pending_calls],
        status_field="supplier_invoice_status",
        invoice_field="purchase_invoice",
        invoice_name=invoice.name,
    )

    return invoice.name, len(pending_calls), total_amount


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mark_calls_invoiced(call_names, status_field, invoice_field, invoice_name):
    placeholders = ", ".join(["%s"] * len(call_names))
    frappe.db.sql(
        f"""UPDATE `tabCall Record`
            SET {status_field} = 'Invoiced', {invoice_field} = %s, modified = NOW()
            WHERE name IN ({placeholders})""",
        [invoice_name] + call_names,
    )


def _period_ends_today(contract, as_of):
    cycle = contract["billing_cycle"]
    if cycle == "Monthly":
        return as_of.day == calendar.monthrange(as_of.year, as_of.month)[1]
    if cycle == "Fortnightly":
        last_day = calendar.monthrange(as_of.year, as_of.month)[1]
        return as_of.day in (15, last_day)
    if cycle == "Weekly":
        start = getdate(contract["start_date"])
        if as_of < start:
            return False
        return ((as_of - start).days + 1) % 7 == 0
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
