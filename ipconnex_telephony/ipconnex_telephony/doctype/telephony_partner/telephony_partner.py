import frappe
from frappe.model.document import Document


class TelephonyPartner(Document):
    def validate(self):
        if not self.customer and not self.supplier:
            frappe.throw("Set at least one of Customer or Supplier on the partner.")

    def onload(self):
        receivable, payable = _fetch_balance(self.customer, self.supplier)
        self.total_receivable = receivable
        self.total_payable = payable
        self.net_balance = receivable - payable

    def on_update(self):
        self._sync_contact()
        self._sync_address()

    def _desired_emails(self):
        out, seen = [], set()
        if self.primary_email:
            out.append((self.primary_email, 1))
            seen.add(self.primary_email.lower())
        for row in self.emails or []:
            if row.email and row.email.lower() not in seen:
                out.append((row.email, int(row.is_primary or 0)))
                seen.add(row.email.lower())
        return out

    def _desired_phones(self):
        out, seen = [], set()
        if self.primary_phone:
            out.append((self.primary_phone, 1))
            seen.add(self.primary_phone)
        for row in self.phones or []:
            if row.phone and row.phone not in seen:
                out.append((row.phone, int(row.is_primary or 0)))
                seen.add(row.phone)
        return out

    def _linked_parties(self):
        links = []
        if self.customer:
            links.append(("Customer", self.customer))
        if self.supplier:
            links.append(("Supplier", self.supplier))
        return links

    def _sync_contact(self):
        emails = self._desired_emails()
        phones = self._desired_phones()
        if not emails and not phones:
            return

        if self.synced_contact and frappe.db.exists("Contact", self.synced_contact):
            contact = frappe.get_doc("Contact", self.synced_contact)
        else:
            contact = frappe.new_doc("Contact")
            contact.first_name = self.display_name or self.partner_name

        contact.email_ids = []
        for email, is_primary in emails:
            contact.append("email_ids", {"email_id": email, "is_primary": is_primary})

        contact.phone_nos = []
        for phone, is_primary in phones:
            contact.append(
                "phone_nos",
                {
                    "phone": phone,
                    "is_primary_phone": is_primary,
                    "is_primary_mobile_no": is_primary,
                },
            )

        contact.links = []
        for dt, dn in self._linked_parties():
            contact.append("links", {"link_doctype": dt, "link_name": dn})

        contact.flags.ignore_permissions = True
        contact.save()

        if self.synced_contact != contact.name:
            self.db_set("synced_contact", contact.name, update_modified=False)

    def _sync_address(self):
        if not (self.address_line_1 or self.city or self.country):
            return

        if self.synced_address and frappe.db.exists("Address", self.synced_address):
            addr = frappe.get_doc("Address", self.synced_address)
        else:
            addr = frappe.new_doc("Address")
            addr.address_type = "Billing"

        addr.address_title = self.display_name or self.partner_name
        addr.address_line1 = self.address_line_1 or ""
        addr.address_line2 = self.address_line_2 or ""
        addr.city = self.city or ""
        addr.country = self.country or ""
        if self.primary_email:
            addr.email_id = self.primary_email
        if self.primary_phone:
            addr.phone = self.primary_phone

        addr.links = []
        for dt, dn in self._linked_parties():
            addr.append("links", {"link_doctype": dt, "link_name": dn})

        addr.flags.ignore_permissions = True
        addr.save()

        if self.synced_address != addr.name:
            self.db_set("synced_address", addr.name, update_modified=False)


@frappe.whitelist()
def get_partner_balance(partner):
    """Return the live outstanding balance for a partner. Used by list view / refresh button."""
    doc = frappe.get_cached_doc("Telephony Partner", partner)
    receivable, payable = _fetch_balance(doc.customer, doc.supplier)
    return {
        "total_receivable": receivable,
        "total_payable": payable,
        "net_balance": receivable - payable,
    }


def _fetch_balance(customer, supplier):
    receivable = 0.0
    payable = 0.0

    if customer:
        result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(outstanding_amount), 0)
            FROM `tabSales Invoice`
            WHERE customer = %s AND docstatus = 1 AND outstanding_amount > 0
            """,
            customer,
        )
        receivable = float(result[0][0] or 0)

    if supplier:
        result = frappe.db.sql(
            """
            SELECT COALESCE(SUM(outstanding_amount), 0)
            FROM `tabPurchase Invoice`
            WHERE supplier = %s AND docstatus = 1 AND outstanding_amount > 0
            """,
            supplier,
        )
        payable = float(result[0][0] or 0)

    return receivable, payable
