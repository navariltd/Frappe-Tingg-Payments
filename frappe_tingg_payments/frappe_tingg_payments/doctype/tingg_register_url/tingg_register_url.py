# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form, get_request_site_address

from ...utils.settings import validate_mode_of_payment_account

API_PATH = "/api/method/frappe_tingg_payments.frappe_tingg_payments.api"


class TinggRegisterURL(Document):
	"""Tingg Register URL Doctype"""

	def validate(self):
		self.set_urls()
		self.set_company()
		validate_mode_of_payment_account(self.mode_of_payment, self.company)

	def set_urls(self):
		# TODO handle sandbox and live environments
		if self.callback_url and self.customer_url:
			return

		site_url = get_request_site_address(True)
		if not self.callback_url:
			self.callback_url = f"{site_url}{API_PATH}.tingg_payment.confirmation"
		if not self.customer_url:
			self.customer_url = f"{site_url}{API_PATH}.customer.get_customer_balance"

	def set_company(self):
		"""The Company always comes from the linked Tingg Settings."""
		company = frappe.db.get_value("Tingg Settings", self.tingg_settings, "company")
		if not company:
			frappe.throw(
				_("Set the Company on Tingg Settings {0} first.").format(
					get_link_to_form("Tingg Settings", self.tingg_settings)
				),
				title=_("Missing Company"),
			)
		self.company = company
