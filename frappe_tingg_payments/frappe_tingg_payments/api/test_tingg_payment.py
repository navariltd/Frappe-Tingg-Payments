# Copyright (c) 2026, Navari Limited and Contributors
# See license.txt

import copy
import datetime
import json
from unittest.mock import MagicMock, patch

from frappe.tests import UnitTestCase

from ..utils.request_log import REDACTED, get_request_id, redact
from .tingg_payment import (
	credentials_valid,
	get_beep_transaction_id,
	parse_payment_date,
	read_fields,
	validate_fields,
)

EXTRA_DATA = {
	"pushToOriginator": True,
	"closedBy": 2,
	"hubID": "280834993",
	"amount": 600,
	"totalAmountCharged": "0.0",
	"msisdn": "260777517357",
	"accountNumber": "kt00199",
	"paybillNumber": "889001291",
}

BODY = {
	"function": "BEEP.pushPaymentStatus",
	"countryCode": "ZMB",
	"payload": {
		"credentials": {"username": "user", "password": "s3cret"},
		"packet": {
			"statusCode": "183",
			"statusDescription": "Payment has been accepted by the merchant",
			"payerTransactionID": "MP261116.0559.A17592",
			"beepTransactionID": "185820348515416518",
			"receiptNumber": "",
			"receiverNarration": "This record has been auto acknowledged",
			"function": "BEEP.pushPaymentStatus",
			"msisdn": "260777517357",
			"serviceCode": "WWSC",
			"paymentDate": "2026-11-16 03:59:10",
			"clientCode": "CELLULANT",
			"extraData": json.dumps(EXTRA_DATA),
		},
	},
}


def make_body(packet_changes=None, extra_changes=None, credentials=None):
	body = copy.deepcopy(BODY)
	packet = body["payload"]["packet"]
	if extra_changes is not None:
		extra = {**EXTRA_DATA, **extra_changes}
		packet["extraData"] = json.dumps({k: v for k, v in extra.items() if v is not None})
	for key, value in (packet_changes or {}).items():
		if value is None:
			packet.pop(key, None)
		else:
			packet[key] = value
	if credentials is not None:
		body["payload"]["credentials"] = credentials
	return body


def mock_settings(username, password):
	settings = MagicMock()
	settings.get.side_effect = lambda key: {"username": username}.get(key)
	settings.get_password.return_value = password
	return settings


class TestReadFields(UnitTestCase):
	def test_reads_packet_and_extra_data(self):
		fields = read_fields(make_body())
		self.assertEqual(fields.status_code, "183")
		self.assertEqual(fields.beep_transaction_id, "185820348515416518")
		self.assertEqual(fields.payer_transaction_id, "MP261116.0559.A17592")
		self.assertEqual(fields.amount, 600)
		self.assertEqual(fields.account_number, "kt00199")
		self.assertEqual(fields.msisdn, "260777517357")
		self.assertEqual(fields.service_code, "WWSC")
		self.assertEqual(fields.client_code, "CELLULANT")
		self.assertEqual(fields.extra_data_text, BODY["payload"]["packet"]["extraData"])
		self.assertEqual(validate_fields(fields), [])

	def test_extra_data_msisdn_wins(self):
		fields = read_fields(make_body({"msisdn": "260000000001"}, {"msisdn": "260000000002"}))
		self.assertEqual(fields.msisdn, "260000000002")

	def test_falls_back_to_packet(self):
		body = make_body(
			{"msisdn": "260000000001", "accountNumber": "ACC-1", "amount": "250"},
			{"msisdn": None, "accountNumber": None, "amount": None},
		)
		fields = read_fields(body)
		self.assertEqual(fields.msisdn, "260000000001")
		self.assertEqual(fields.account_number, "ACC-1")
		self.assertEqual(fields.amount, "250")
		self.assertEqual(validate_fields(fields), [])

	def test_optional_fields_captured_when_sent(self):
		fields = read_fields(
			make_body({"customerName": "Jane", "serviceID": "42"}, {"payerNarration": "Paid"})
		)
		self.assertEqual(fields.customer_name, "Jane")
		self.assertEqual(fields.service_id, "42")
		self.assertEqual(fields.payer_narration, "Paid")

	def test_extra_data_required(self):
		errors = validate_fields(read_fields(make_body({"extraData": None})))
		self.assertIn("extraData is required and must be a JSON object", errors)

		errors = validate_fields(read_fields(make_body({"extraData": "not json"})))
		self.assertIn("extraData is required and must be a JSON object", errors)

	def test_amount_and_account_number_required(self):
		errors = validate_fields(read_fields(make_body(extra_changes={"amount": 0, "accountNumber": None})))
		self.assertIn("amount must be a number greater than zero", errors)
		self.assertIn("accountNumber is required", errors)

	def test_beep_transaction_id_from_body_and_response(self):
		self.assertEqual(get_beep_transaction_id(BODY), "185820348515416518")
		self.assertEqual(get_beep_transaction_id({"beepTransactionID": "123"}), "123")
		self.assertEqual(get_request_id(BODY, get_beep_transaction_id), "185820348515416518")
		self.assertIsNone(get_request_id({}, get_beep_transaction_id))


class TestCredentials(UnitTestCase):
	def check(self, settings, body):
		with patch(f"{credentials_valid.__module__}.get_active_tingg_settings", return_value=settings):
			return credentials_valid(body)

	def test_not_configured_accepts(self):
		self.assertTrue(self.check(None, make_body()))
		self.assertTrue(self.check(mock_settings(None, None), make_body()))

	def test_matching_credentials(self):
		self.assertTrue(self.check(mock_settings("user", "s3cret"), make_body()))

	def test_wrong_or_missing_credentials(self):
		settings = mock_settings("user", "s3cret")
		self.assertFalse(self.check(settings, make_body(credentials={"username": "user", "password": "x"})))
		self.assertFalse(self.check(settings, make_body(credentials={"username": "x", "password": "s3cret"})))
		self.assertFalse(self.check(settings, make_body(credentials={})))


class TestPaymentDate(UnitTestCase):
	def test_naive_date_is_utc(self):
		with patch("frappe.utils.data.get_system_timezone", return_value="Africa/Lusaka"):
			self.assertEqual(
				parse_payment_date("2026-11-16 03:59:10"),
				datetime.datetime(2026, 11, 16, 5, 59, 10),
			)

	def test_aware_date_is_converted(self):
		with patch("frappe.utils.data.get_system_timezone", return_value="Africa/Lusaka"):
			self.assertEqual(
				parse_payment_date("2026-11-16T03:59:10+01:00"),
				datetime.datetime(2026, 11, 16, 4, 59, 10),
			)

	def test_missing_date_is_now(self):
		self.assertIsInstance(parse_payment_date(None), datetime.datetime)
		self.assertIsInstance(parse_payment_date("garbage"), datetime.datetime)


class TestRedact(UnitTestCase):
	def test_password_masked(self):
		redacted = redact(BODY)
		self.assertEqual(redacted["payload"]["credentials"]["password"], REDACTED)
		self.assertEqual(redacted["payload"]["credentials"]["username"], "user")
		# Nested JSON strings without secrets are kept exactly as received.
		self.assertEqual(redacted["payload"]["packet"]["extraData"], BODY["payload"]["packet"]["extraData"])
		self.assertEqual(BODY["payload"]["credentials"]["password"], "s3cret")

	def test_password_in_json_string_masked(self):
		redacted = redact({"payload": json.dumps({"credentials": {"password": "s3cret"}})})
		self.assertNotIn("s3cret", redacted["payload"])
