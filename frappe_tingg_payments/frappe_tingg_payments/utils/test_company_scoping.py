# Copyright (c) 2026, Navari Limited and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from .settings import validate_mode_of_payment_account

REGISTER_MODULE = (
	"frappe_tingg_payments.frappe_tingg_payments.doctype.tingg_payment_register.tingg_payment_register"
)
PAYMENT_MODULE = "frappe_tingg_payments.frappe_tingg_payments.api.tingg_payment"
REGISTER_URL_MODULE = (
	"frappe_tingg_payments.frappe_tingg_payments.doctype.tingg_register_url.tingg_register_url"
)


def get_mode_of_payment_account():
	"""Any Mode of Payment with a default account, as (mode_of_payment, company)."""
	row = frappe.db.get_value(
		"Mode of Payment Account",
		{"parenttype": "Mode of Payment", "default_account": ["is", "set"]},
		["parent", "company"],
	)
	return row or (None, None)


class TestModeOfPaymentAccount(UnitTestCase):
	def test_account_for_company_passes(self):
		mode_of_payment, company = get_mode_of_payment_account()
		if not mode_of_payment:
			self.skipTest("No Mode of Payment with a default account on this site")
		validate_mode_of_payment_account(mode_of_payment, company)

	def test_missing_account_fails(self):
		mode_of_payment, _company = get_mode_of_payment_account()
		if not mode_of_payment:
			self.skipTest("No Mode of Payment with a default account on this site")
		with self.assertRaises(frappe.ValidationError):
			validate_mode_of_payment_account(mode_of_payment, "_Tingg Company That Does Not Exist")

	def test_nothing_to_check(self):
		validate_mode_of_payment_account(None, "Any")
		validate_mode_of_payment_account("Any", None)


class TestPaymentRegisterCompany(UnitTestCase):
	def make_register(self, **values):
		doc = frappe.new_doc("Tingg Payment Register")
		doc.update(values)
		return doc

	def test_company_defaults_from_settings(self):
		doc = self.make_register(company=None, currency=None)
		with (
			patch(f"{REGISTER_MODULE}.get_tingg_company", return_value="Tingg Co"),
			patch(f"{REGISTER_MODULE}.get_active_register_url", return_value=None),
			patch(f"{REGISTER_MODULE}.get_company_currency", return_value="ZMW"),
		):
			doc.set_posting_defaults()
			doc.validate_company()
		self.assertEqual(doc.company, "Tingg Co")
		self.assertEqual(doc.currency, "ZMW")

	def test_other_company_rejected(self):
		doc = self.make_register(company="Other Co")
		with patch(f"{REGISTER_MODULE}.get_tingg_company", return_value="Tingg Co"):
			with self.assertRaises(frappe.ValidationError):
				doc.validate_company()

	def test_no_settings_company_not_checked(self):
		doc = self.make_register(company="Other Co")
		with patch(f"{REGISTER_MODULE}.get_tingg_company", return_value=None):
			doc.validate_company()


class TestBuildRegister(UnitTestCase):
	"""new_doc pre-fills the default Company and global Currency; the API must replace both."""

	def build(self, company, company_currency):
		from ..api.tingg_payment import build_register, read_fields

		fields = read_fields({"beepTransactionID": "1", "accountNumber": "A", "amount": 1})
		with (
			patch(f"{PAYMENT_MODULE}.get_tingg_company", return_value=company),
			patch(f"{PAYMENT_MODULE}.get_company_currency", return_value=company_currency),
			patch(f"{PAYMENT_MODULE}.find_customer", return_value=None),
		):
			return build_register(fields)

	def test_company_and_currency_from_settings(self):
		doc = self.build("Tingg Co", "XYZ")
		self.assertEqual(doc.company, "Tingg Co")
		self.assertEqual(doc.currency, "XYZ")

	def test_no_company_leaves_currency_to_validate(self):
		doc = self.build(None, "XYZ")
		self.assertIsNone(doc.company)
		self.assertIsNone(doc.currency)


class TestRegisterURLCompany(UnitTestCase):
	def test_company_comes_from_settings(self):
		doc = frappe.new_doc("Tingg Register URL")
		doc.tingg_settings = "Some Settings"
		doc.company = "Typed Co"
		with patch(f"{REGISTER_URL_MODULE}.frappe.db.get_value", return_value="Tingg Co"):
			doc.set_company()
		self.assertEqual(doc.company, "Tingg Co")

	def test_settings_without_company_rejected(self):
		doc = frappe.new_doc("Tingg Register URL")
		doc.tingg_settings = "Some Settings"
		with patch(f"{REGISTER_URL_MODULE}.frappe.db.get_value", return_value=None):
			with self.assertRaises(frappe.ValidationError):
				doc.set_company()
