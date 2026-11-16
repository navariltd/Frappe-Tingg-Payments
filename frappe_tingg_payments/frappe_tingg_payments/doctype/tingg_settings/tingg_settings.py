# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import call_hook_method
from payments.payment_gateways.doctype.mpesa_settings.mpesa_settings import (
	create_mode_of_payment,
)
from payments.utils import create_payment_gateway

from ...utils.settings import validate_mode_of_payment_account

REGISTER_URL_DOCTYPE = "Tingg Register URL"


class TinggSettings(Document):
	"""Tingg Settings Doctype"""

	def validate(self) -> None:
		self.validate_register_url_accounts()

	def validate_register_url_accounts(self) -> None:
		"""The Register URL's Mode of Payment must have an account for the new Company."""
		if self.is_new() or not self.has_value_changed("company"):
			return

		for mode_of_payment in frappe.get_all(
			REGISTER_URL_DOCTYPE, filters={"tingg_settings": self.name}, pluck="mode_of_payment"
		):
			validate_mode_of_payment_account(mode_of_payment, self.company)

	def on_update(self) -> None:
		"""On Update Hook"""
		create_payment_gateway(
			"Tingg-" + self.payment_gateway_name,
			settings="Tingg Settings",
			controller=self.payment_gateway_name,
		)

		call_hook_method(
			"payment_gateway_enabled",
			gateway="Tingg-" + self.payment_gateway_name,
			payment_channel="Phone",
		)

		create_mode_of_payment("Tingg-" + self.payment_gateway_name, payment_type="Phone")

		self.sync_register_url_company()

	def sync_register_url_company(self) -> None:
		"""Keep the Company on the linked Register URL the same as these settings."""
		frappe.db.set_value(
			REGISTER_URL_DOCTYPE,
			{"tingg_settings": self.name, "company": ["!=", self.company]},
			"company",
			self.company,
		)
