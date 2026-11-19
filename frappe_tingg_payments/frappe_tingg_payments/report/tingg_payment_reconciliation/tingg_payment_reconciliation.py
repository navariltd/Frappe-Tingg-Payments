# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.utils import add_days, getdate

REGISTER_DOCTYPE = "Tingg Payment Register"
DOCUMENT_STATUSES = {"Draft": 0, "Submitted": 1, "Cancelled": 2}
PAYMENT_STATUSES = ("Pending", "Unmatched", "Failed", "Processed", "Cancelled")


def execute(filters=None):
	frappe.has_permission(REGISTER_DOCTYPE, "read", throw=True)
	frappe.has_permission(REGISTER_DOCTYPE, "report", throw=True)
	rows = frappe.get_list(
		REGISTER_DOCTYPE,
		fields=[
			"company",
			"customer",
			"amount_paid",
			"currency",
			"status",
			"docstatus",
			"payment_entry",
			"beep_transaction_id",
			"payer_transaction_id",
		],
		filters=get_filters(frappe._dict(filters or {})),
		order_by="payment_date desc, creation desc, name desc",
		limit_page_length=0,
	)
	status_labels = {0: _("Draft"), 1: _("Submitted"), 2: _("Cancelled")}
	for row in rows:
		row["document_status"] = status_labels.get(row.pop("docstatus"), _("Unknown"))
		row["status"] = _(row["status"]) if row.get("status") else ""

	return (
		get_columns(),
		rows,
		_(
			"Status describes Tingg processing; Document Status describes the payment register. "
			"Processed does not guarantee invoice allocation. Open the Payment Entry to check allocation."
		),
	)


def get_filters(filters):
	conditions = []
	from_date = getdate(filters.from_date) if filters.from_date else None
	to_date = getdate(filters.to_date) if filters.to_date else None
	if from_date and to_date and from_date > to_date:
		frappe.throw(_("From Date cannot be after To Date."))
	if from_date:
		conditions.append(["payment_date", ">=", from_date])
	if to_date:
		# Payment Date is a Datetime: include the entire last day, not just midnight.
		conditions.append(["payment_date", "<", add_days(to_date, 1)])
	for field in ("company", "customer", "beep_transaction_id"):
		if filters.get(field):
			conditions.append([field, "=", filters[field]])
	if filters.status:
		if filters.status not in PAYMENT_STATUSES:
			frappe.throw(_("Invalid Status."))
		conditions.append(["status", "=", filters.status])
	if filters.document_status:
		if filters.document_status not in DOCUMENT_STATUSES:
			frappe.throw(_("Invalid Document Status."))
		conditions.append(["docstatus", "=", DOCUMENT_STATUSES[filters.document_status]])
	return conditions


def get_columns():
	return [
		{
			"fieldname": "company",
			"label": _("Company"),
			"fieldtype": "Link",
			"options": "Company",
			"width": 180,
		},
		{
			"fieldname": "customer",
			"label": _("Customer"),
			"fieldtype": "Link",
			"options": "Customer",
			"width": 180,
		},
		{
			"fieldname": "amount_paid",
			"label": _("Amount Paid"),
			"fieldtype": "Currency",
			"options": "currency",
			"width": 140,
		},
		{"fieldname": "status", "label": _("Status"), "fieldtype": "Data", "width": 120},
		{"fieldname": "document_status", "label": _("Document Status"), "fieldtype": "Data", "width": 140},
		{
			"fieldname": "payment_entry",
			"label": _("Payment Entry"),
			"fieldtype": "Link",
			"options": "Payment Entry",
			"width": 190,
		},
		{
			"fieldname": "beep_transaction_id",
			"label": _("Beep Transaction ID"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "payer_transaction_id",
			"label": _("Payer Transaction ID"),
			"fieldtype": "Data",
			"width": 200,
		},
		{
			"fieldname": "currency",
			"label": _("Currency"),
			"fieldtype": "Link",
			"options": "Currency",
			"hidden": 1,
		},
	]
