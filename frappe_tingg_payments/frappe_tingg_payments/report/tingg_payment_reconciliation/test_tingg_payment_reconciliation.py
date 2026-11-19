# Copyright (c) 2026, Navari Limited and contributors
# For license information, please see license.txt

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from . import tingg_payment_reconciliation as report


class TestTinggPaymentReconciliation(TestCase):
	def setUp(self):
		# Keep these unit tests independent of a site's translation cache and language.
		translation = patch.object(report, "_", side_effect=lambda text: text)
		translation.start()
		self.addCleanup(translation.stop)

	def test_document_status_is_independent_of_processing_status(self):
		rows = [
			{"docstatus": 0, "status": "Failed", "customer": None, "payment_entry": None},
			{"docstatus": 1, "status": "Processed", "payment_entry": "TEST-PE"},
			{"docstatus": 2, "status": "Cancelled"},
		]
		with patch.object(report.frappe, "has_permission"), patch.object(
			report.frappe, "get_list", return_value=rows
		) as query:
			columns, data, message = report.execute()
		self.assertEqual([row["document_status"] for row in data], ["Draft", "Submitted", "Cancelled"])
		self.assertEqual(data[0]["status"], "Failed")
		self.assertIsNone(data[0]["customer"])
		self.assertIsNone(data[0]["payment_entry"])
		self.assertIn("does not guarantee invoice allocation", message)
		self.assertEqual(query.call_args.kwargs["limit_page_length"], 0)
		self.assertNotIn("ignore_permissions", query.call_args.kwargs)
		self.assertEqual(columns[2]["options"], "currency")

	def test_all_processing_statuses_remain_distinct(self):
		rows = [{"docstatus": 0, "status": status} for status in report.PAYMENT_STATUSES]
		with patch.object(report.frappe, "has_permission"), patch.object(
			report.frappe, "get_list", return_value=rows
		):
			_, data, _ = report.execute()
		self.assertEqual([row["status"] for row in data], list(report.PAYMENT_STATUSES))

	def test_permission_denial_prevents_query(self):
		for denied_permission in ("read", "report"):
			with self.subTest(permission=denied_permission):

				def check_permission(doctype, permission, throw=False):
					self.assertEqual(doctype, report.REGISTER_DOCTYPE)
					self.assertTrue(throw)
					if permission == denied_permission:
						raise frappe.PermissionError

				with patch.object(
					report.frappe, "has_permission", side_effect=check_permission
				), patch.object(report.frappe, "get_list") as query:
					with self.assertRaises(frappe.PermissionError):
						report.execute()
				query.assert_not_called()

	def test_empty_results_keep_columns(self):
		with patch.object(report.frappe, "has_permission"), patch.object(
			report.frappe, "get_list", return_value=[]
		):
			columns, rows, _ = report.execute()
		self.assertEqual(rows, [])
		self.assertEqual(len([column for column in columns if not column.get("hidden")]), 8)

	def test_currency_amount_and_transaction_id_are_preserved(self):
		transaction_id = "185820348515416518"
		row = {
			"docstatus": 1,
			"status": "Processed",
			"amount_paid": 1234.56,
			"currency": "ZMW",
			"beep_transaction_id": transaction_id,
			"payer_transaction_id": "000185820348515416518",
		}
		with patch.object(report.frappe, "has_permission"), patch.object(
			report.frappe, "get_list", return_value=[row]
		):
			_, data, _ = report.execute()
		self.assertEqual(data[0]["amount_paid"], 1234.56)
		self.assertEqual(data[0]["currency"], "ZMW")
		self.assertEqual(data[0]["beep_transaction_id"], transaction_id)
		self.assertEqual(data[0]["payer_transaction_id"], "000185820348515416518")

	def test_date_range_includes_whole_final_day(self):
		conditions = report.get_filters(frappe._dict(from_date="2026-11-18", to_date="2026-11-18"))
		self.assertEqual(
			conditions,
			[
				["payment_date", ">=", date(2026, 11, 18)],
				["payment_date", "<", date(2026, 11, 19)],
			],
		)

	def test_optional_date_bounds(self):
		self.assertEqual(report.get_filters(frappe._dict()), [])
		self.assertEqual(len(report.get_filters(frappe._dict(from_date="2026-11-18"))), 1)
		self.assertEqual(len(report.get_filters(frappe._dict(to_date="2026-11-18"))), 1)

	def test_draft_filter_is_not_dropped_as_falsy_zero(self):
		self.assertEqual(report.get_filters(frappe._dict(document_status="Draft")), [["docstatus", "=", 0]])

	def test_exact_match_filters(self):
		filters = frappe._dict(
			company="Test Company",
			customer="Test Customer",
			status="Unmatched",
			document_status="Submitted",
			beep_transaction_id="123",
		)
		self.assertEqual(
			report.get_filters(filters),
			[
				["company", "=", "Test Company"],
				["customer", "=", "Test Customer"],
				["beep_transaction_id", "=", "123"],
				["status", "=", "Unmatched"],
				["docstatus", "=", 1],
			],
		)

	def test_invalid_filters_are_rejected_before_query(self):
		for filters in (
			{"from_date": "2026-11-19", "to_date": "2026-11-18"},
			{"status": "Paid"},
			{"document_status": "Processed"},
		):
			with self.subTest(filters=filters), patch.object(report.frappe, "has_permission"), patch.object(
				report.frappe, "throw", side_effect=frappe.ValidationError
			), patch.object(report.frappe, "get_list") as query:
				with self.assertRaises(frappe.ValidationError):
					report.execute(filters)
				query.assert_not_called()
