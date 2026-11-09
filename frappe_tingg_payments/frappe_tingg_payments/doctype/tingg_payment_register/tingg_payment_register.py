# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, get_link_to_form, getdate

from ...utils.helpers import create_payment_entry, reconcile_payment_entry
from ...utils.settings import get_active_register_url

RECONCILE_SAVEPOINT = "tingg_register_reconcile"


class TinggPaymentRegister(Document):
	def validate(self):
		if self.amended_from:
			frappe.throw(
				_(
					"Tingg Payment Registers cannot be amended because the Beep Transaction ID must stay unique."
				)
			)
		self.set_posting_defaults()
		self.update_draft_status()

	def set_posting_defaults(self):
		if not self.currency:
			self.currency = frappe.defaults.get_global_default("currency")

		if self.company and self.mode_of_payment:
			return

		register_url = get_active_register_url()
		if register_url:
			self.company = self.company or register_url.company
			self.mode_of_payment = self.mode_of_payment or register_url.mode_of_payment

	def update_draft_status(self):
		if self.docstatus == 0 and self.status != "Failed":
			self.status = "Pending" if self.customer else "Unmatched"

	def before_submit(self):
		self.validate_required_for_posting()
		self.payment_entry = self.create_payment_entry()
		self.status = "Processed"
		self.processing_error = None

	def validate_required_for_posting(self):
		missing = []
		if flt(self.amount_paid) <= 0:
			missing.append(_("Amount Paid"))
		if not self.company:
			missing.append(_("Company"))
		if not self.customer:
			missing.append(_("Customer"))
		if not self.mode_of_payment:
			missing.append(_("Mode of Payment"))
		if not self.currency:
			missing.append(_("Currency"))

		if missing:
			frappe.throw(
				_("Cannot post the payment, the following are missing: {0}").format(", ".join(missing)),
				title=_("Missing Values"),
			)

	def create_payment_entry(self):
		existing = frappe.db.get_value(
			"Payment Entry",
			{
				"reference_no": self.beep_transaction_id,
				"party_type": "Customer",
				"party": self.customer,
				"docstatus": ["!=", 2],
			},
		)
		if existing:
			frappe.throw(
				_("Payment Entry {0} already exists for Beep Transaction ID {1}").format(
					get_link_to_form("Payment Entry", existing), self.beep_transaction_id
				),
				title=_("Duplicate Payment"),
			)

		posting_date = getdate(self.payment_date) if self.payment_date else None
		payment_entry = create_payment_entry(
			company=self.company,
			customer=self.customer,
			amount=self.amount_paid,
			currency=self.currency,
			mode_of_payment=self.mode_of_payment,
			reference_date=posting_date,
			reference_no=self.beep_transaction_id,
			posting_date=posting_date,
			submit=self.submit_payment,
		)
		return payment_entry.name

	def on_submit(self):
		self.reconcile_payment()

	def reconcile_payment(self):
		"""Allocate the payment against outstanding invoices.

		The payment stays posted (unallocated) if reconciliation fails, so a failure
		here is logged rather than raised.
		"""
		if not self.submit_payment or not self.payment_entry:
			return

		frappe.db.savepoint(RECONCILE_SAVEPOINT)
		try:
			reconcile_payment_entry(self.company, self.customer, self.payment_entry)
		except Exception:
			frappe.db.rollback(save_point=RECONCILE_SAVEPOINT)
			frappe.log_error(
				title=_("Tingg payment {0} could not be reconciled").format(self.beep_transaction_id),
				message=frappe.get_traceback(),
				reference_doctype=self.doctype,
				reference_name=self.name,
			)

	def on_cancel(self):
		self.db_set("status", "Cancelled")
