import datetime
import json

import frappe
from frappe import _
from frappe.utils import (
	convert_utc_to_system_timezone,
	cstr,
	flt,
	get_datetime,
	now_datetime,
)

from ..utils.request_log import log_tingg_request, set_request_reference

REGISTER_DOCTYPE = "Tingg Payment Register"

# Acknowledgement codes returned to Tingg in `statusCode`.
# TODO: confirm STATUS_REJECTED with Cellulant.
STATUS_ACCEPTED = "140"
STATUS_REJECTED = "141"

SUBMIT_SAVEPOINT = "tingg_register_submit"


# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
@frappe.whitelist(allow_guest=True, methods=["POST"])
@log_tingg_request("Payment Confirmation", request_id_key="beepTransactionID")
def confirmation(**kwargs):
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	frappe.set_user("Administrator")

	payload = parse_payload(kwargs)

	beep_transaction_id = cstr(payload.get("beepTransactionID")).strip()
	payer_transaction_id = cstr(payload.get("payerTransactionID")).strip()

	payload_dump = json.dumps(payload, indent=2, default=str)

	errors = validate_payload(payload, beep_transaction_id)
	if errors:
		error_lines = "\n".join(errors)
		frappe.log_error(
			title=_("Tingg payment confirmation rejected"),
			message=f"{error_lines}\n\nPayload:\n{payload_dump}",
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(
			beep_transaction_id,
			payer_transaction_id,
			STATUS_REJECTED,
			"; ".join(errors),
			http_status_code=400,
		)

	try:
		register_name = get_or_create_register(payload, beep_transaction_id)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Tingg payment {0} could not be recorded").format(beep_transaction_id),
			message=f"{frappe.get_traceback()}\n\nPayload:\n{payload_dump}",
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(
			beep_transaction_id,
			payer_transaction_id,
			STATUS_REJECTED,
			"Payment could not be recorded",
			http_status_code=500,
		)

	set_request_reference(REGISTER_DOCTYPE, register_name)
	return process_register(register_name)


def parse_payload(kwargs):
	"""Return the callback body as a dict.

	Frappe only parses the body as JSON when the request is sent with
	`Content-Type: application/json`. With any other content type (or none) the
	JSON stays an unparsed string, so fall back to reading the raw body.
	"""
	payload = frappe._dict(kwargs)
	payload.pop("cmd", None)
	if payload.get("beepTransactionID"):
		return payload

	request = getattr(frappe.local, "request", None)
	body = load_json(request.get_data(as_text=True)) if request else None
	if isinstance(body, dict):
		return frappe._dict(body)

	return payload


def load_json(value):
	"""Parse a JSON string, also unwrapping a JSON document that was encoded twice."""
	for _attempt in range(2):
		if not isinstance(value, str):
			break
		try:
			value = json.loads(value)
		except ValueError:
			return None
	return value


def validate_payload(payload, beep_transaction_id):
	errors = []
	if not beep_transaction_id:
		errors.append("beepTransactionID is required")
	if flt(payload.get("amountPaid")) <= 0:
		errors.append("amountPaid must be a number greater than zero")
	return errors


def get_or_create_register(payload, beep_transaction_id):
	"""Return the register for this Beep transaction, creating it on first sight.

	The register is committed straight away so that the payment is on record even
	if posting it fails later on.
	"""
	existing = frappe.db.get_value(REGISTER_DOCTYPE, {"beep_transaction_id": beep_transaction_id})
	if existing:
		return existing

	doc = build_register(payload, beep_transaction_id)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		frappe.db.rollback()
		frappe.clear_messages()
		return frappe.db.get_value(REGISTER_DOCTYPE, {"beep_transaction_id": beep_transaction_id})

	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()
	return doc.name


def build_register(payload, beep_transaction_id):
	doc = frappe.new_doc(REGISTER_DOCTYPE)
	doc.beep_transaction_id = beep_transaction_id
	doc.payer_transaction_id = cstr(payload.get("payerTransactionID")).strip()
	doc.account_number = cstr(payload.get("accountNumber")).strip()
	doc.customer = find_customer(doc.account_number)
	doc.customer_name = payload.get("customerName")
	doc.msisdn = cstr(payload.get("msisdn"))
	doc.hashed_msisdn = cstr(payload.get("hashed_msisdn"))
	doc.amount_paid = flt(payload.get("amountPaid"))
	doc.status_description = cstr(payload.get("statusDescription"))
	doc.receiver_narration = cstr(payload.get("receiverNarration"))
	doc.payer_narration = cstr(payload.get("payerNarration"))
	doc.extra_data = to_text(payload.get("extraData"))
	doc.payment_date = parse_payment_date(payload.get("paymentDate"))
	doc.client_code = cstr(payload.get("clientCode"))
	doc.service_id = cstr(payload.get("serviceID"))
	doc.service_code = cstr(payload.get("serviceCode"))
	doc.merchant_payment_ids = to_text(payload.get("merchantPaymentIDs"))
	doc.submit_payment = 1
	return doc


def process_register(register_name):
	# Lock the row so that concurrent retries for the same transaction wait for
	# the first one to finish instead of posting the payment twice.
	frappe.db.get_value(REGISTER_DOCTYPE, register_name, "name", for_update=True)
	doc = frappe.get_doc(REGISTER_DOCTYPE, register_name)

	if doc.docstatus != 0:
		# Already handled: acknowledge again so Tingg stops retrying.
		return respond(
			doc.beep_transaction_id,
			doc.payer_transaction_id,
			STATUS_ACCEPTED,
			"Payment already received",
		)

	if not doc.customer:
		# The customer may have been created since the last attempt.
		doc.customer = find_customer(doc.account_number)

	if not doc.customer:
		doc.save(ignore_permissions=True)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(
			doc.beep_transaction_id,
			doc.payer_transaction_id,
			STATUS_ACCEPTED,
			"Payment received, pending manual allocation",
		)

	frappe.db.savepoint(SUBMIT_SAVEPOINT)
	try:
		doc.submit()
	except Exception as e:
		frappe.db.rollback(save_point=SUBMIT_SAVEPOINT)
		frappe.db.set_value(
			REGISTER_DOCTYPE,
			register_name,
			{"status": "Failed", "processing_error": cstr(e) or e.__class__.__name__},
			update_modified=False,
		)
		frappe.log_error(
			title=_("Tingg payment {0} could not be posted").format(doc.beep_transaction_id),
			message=frappe.get_traceback(),
			reference_doctype=REGISTER_DOCTYPE,
			reference_name=register_name,
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(
			doc.beep_transaction_id,
			doc.payer_transaction_id,
			STATUS_REJECTED,
			"Payment received but could not be posted",
			http_status_code=500,
		)

	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()
	return respond(
		doc.beep_transaction_id,
		doc.payer_transaction_id,
		STATUS_ACCEPTED,
		"Payment pushed successfully",
	)


def respond(
	beep_transaction_id,
	payer_transaction_id,
	status_code,
	status_description,
	http_status_code=200,
):
	frappe.clear_messages()
	frappe.response["beepTransactionID"] = beep_transaction_id
	frappe.response["payerTransactionID"] = payer_transaction_id
	frappe.response["statusCode"] = status_code
	frappe.response["statusDescription"] = status_description
	frappe.response["http_status_code"] = http_status_code


def find_customer(account_number):
	if not account_number:
		return None
	return frappe.db.exists("Customer", account_number) or None


def to_text(value):
	if value in (None, ""):
		return None
	if isinstance(value, (dict | list)):
		return json.dumps(value)
	return cstr(value)


def parse_payment_date(value):
	try:
		payment_date = get_datetime(value) if value else None
	except Exception:
		payment_date = None

	if not payment_date:
		return now_datetime()

	if payment_date.tzinfo:
		payment_date = convert_utc_to_system_timezone(payment_date.astimezone(datetime.timezone.utc)).replace(
			tzinfo=None
		)

	return payment_date
