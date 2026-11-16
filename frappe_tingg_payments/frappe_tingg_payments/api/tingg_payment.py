import datetime
import hmac
import json

import frappe
from erpnext import get_company_currency
from frappe import _
from frappe.utils import (
	convert_utc_to_system_timezone,
	cstr,
	flt,
	get_datetime,
	now_datetime,
)

from ..utils.request_log import load_json, log_tingg_request, redact, set_request_reference
from ..utils.settings import get_active_tingg_settings, get_tingg_company

REGISTER_DOCTYPE = "Tingg Payment Register"

# `statusCode` Tingg sends for a payment the merchant accepted. Only these are recorded.
PAYMENT_STATUS_ACCEPTED = "183"

# Acknowledgement codes returned to Tingg in `statusCode`.
STATUS_RECEIVED = "188"
STATUS_REJECTED = "180"

SUBMIT_SAVEPOINT = "tingg_register_submit"


def get_beep_transaction_id(data):
	"""The Beep Transaction ID of a callback body, or of the response sent back."""
	if not isinstance(data, dict):
		return None
	return cstr(get_packet(data).get("beepTransactionID")).strip() or None


# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
@frappe.whitelist(allow_guest=True, methods=["POST"])
@log_tingg_request("Payment Confirmation", request_id_key=get_beep_transaction_id)
def confirmation(**kwargs):
	# nosemgrep: frappe-semgrep-rules.rules.security.frappe-setuser
	frappe.set_user("Administrator")

	body = parse_body(kwargs)
	fields = read_fields(body)
	payload_dump = json.dumps(redact(body), indent=2, default=str)

	if not credentials_valid(body):
		frappe.log_error(
			title=_("Tingg payment confirmation rejected: invalid credentials"),
			message=f"Payload:\n{payload_dump}",
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(fields, STATUS_REJECTED, "Invalid credentials", http_status_code=401)

	if fields.status_code != PAYMENT_STATUS_ACCEPTED:
		# Not an accepted payment (e.g. failed or reversed): keep a trace, record nothing.
		frappe.log_error(
			title=_("Tingg payment status {0} not recorded").format(fields.status_code or _("(missing)")),
			message=f"{fields.status_description}\n\nPayload:\n{payload_dump}",
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(
			fields,
			STATUS_RECEIVED,
			f"Payment status {fields.status_code or '(missing)'} received, payment not recorded",
		)

	errors = validate_fields(fields)
	if errors:
		error_lines = "\n".join(errors)
		frappe.log_error(
			title=_("Tingg payment confirmation rejected"),
			message=f"{error_lines}\n\nPayload:\n{payload_dump}",
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(fields, STATUS_REJECTED, "; ".join(errors), http_status_code=400)

	try:
		register_name = get_or_create_register(fields)
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Tingg payment {0} could not be recorded").format(fields.beep_transaction_id),
			message=f"{frappe.get_traceback()}\n\nPayload:\n{payload_dump}",
		)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(fields, STATUS_REJECTED, "Payment could not be recorded", http_status_code=500)

	set_request_reference(REGISTER_DOCTYPE, register_name)
	return process_register(register_name)


def parse_body(kwargs):
	"""Return the callback body as a dict.

	Frappe only parses the body as JSON when the request is sent with
	`Content-Type: application/json`. With any other content type (or none) the
	JSON stays an unparsed string, so fall back to reading the raw body.
	"""
	body = frappe._dict(kwargs)
	body.pop("cmd", None)
	if body.get("payload") or body.get("beepTransactionID"):
		return body

	request = getattr(frappe.local, "request", None)
	raw = load_json(request.get_data(as_text=True)) if request else None
	if isinstance(raw, dict):
		return frappe._dict(raw)

	return body


def as_dict(value):
	"""`value` as a dict, parsing it first if it arrived as a JSON string."""
	value = load_json(value) if isinstance(value, str) else value
	return frappe._dict(value) if isinstance(value, dict) else None


def get_payload(body):
	return as_dict(body.get("payload")) or frappe._dict()


def get_packet(body):
	"""The `payload.packet` of a callback; a flat body is treated as the packet itself."""
	return as_dict(get_payload(body).get("packet")) or frappe._dict(body)


def first_value(*values):
	return next((value for value in values if value not in (None, "")), None)


def read_fields(body):
	"""Collect the values the register needs from the packet and its `extraData`.

	`msisdn`, `accountNumber` and the amount are read from `extraData` first and
	fall back to the packet. Everything else is read from the packet first.
	"""
	packet = get_packet(body)
	extra_data = as_dict(packet.get("extraData"))
	extra = extra_data or frappe._dict()

	def from_packet(key):
		return first_value(packet.get(key), extra.get(key))

	def from_extra(key, *packet_keys):
		return first_value(extra.get(key), *(packet.get(k) for k in (key, *packet_keys)))

	return frappe._dict(
		status_code=cstr(packet.get("statusCode")).strip(),
		status_description=cstr(packet.get("statusDescription")),
		beep_transaction_id=cstr(packet.get("beepTransactionID")).strip(),
		payer_transaction_id=cstr(packet.get("payerTransactionID")).strip(),
		extra_data=extra_data,
		extra_data_text=to_text(packet.get("extraData")),
		amount=from_extra("amount", "amountPaid"),
		account_number=cstr(from_extra("accountNumber")).strip(),
		msisdn=cstr(from_extra("msisdn")),
		customer_name=from_packet("customerName"),
		hashed_msisdn=cstr(from_packet("hashed_msisdn")),
		receiver_narration=cstr(from_packet("receiverNarration")),
		payer_narration=cstr(from_packet("payerNarration")),
		payment_date=from_packet("paymentDate"),
		client_code=cstr(from_packet("clientCode")),
		service_id=cstr(from_packet("serviceID")),
		service_code=cstr(from_packet("serviceCode")),
		merchant_payment_ids=to_text(from_packet("merchantPaymentIDs")),
	)


def credentials_valid(body):
	"""Check `payload.credentials` against the active Tingg Settings.

	Nothing is checked until a username or password is set on Tingg Settings.
	"""
	settings = get_active_tingg_settings()
	if not settings:
		return True

	expected_username = cstr(settings.get("username"))
	expected_password = cstr(settings.get_password("password", raise_exception=False))
	if not expected_username and not expected_password:
		return True

	credentials = as_dict(get_payload(body).get("credentials")) or frappe._dict()
	username_ok = hmac.compare_digest(cstr(credentials.get("username")).encode(), expected_username.encode())
	password_ok = hmac.compare_digest(cstr(credentials.get("password")).encode(), expected_password.encode())
	return username_ok and password_ok


def validate_fields(fields):
	errors = []
	if not fields.beep_transaction_id:
		errors.append("beepTransactionID is required")
	if fields.extra_data is None:
		errors.append("extraData is required and must be a JSON object")
	if flt(fields.amount) <= 0:
		errors.append("amount must be a number greater than zero")
	if not fields.account_number:
		errors.append("accountNumber is required")
	return errors


def get_or_create_register(fields):
	"""Return the register for this Beep transaction, creating it on first sight.

	The register is committed straight away so that the payment is on record even
	if posting it fails later on.
	"""
	beep_transaction_id = fields.beep_transaction_id
	existing = frappe.db.get_value(REGISTER_DOCTYPE, {"beep_transaction_id": beep_transaction_id})
	if existing:
		return existing

	doc = build_register(fields)
	try:
		doc.insert(ignore_permissions=True)
	except frappe.UniqueValidationError:
		frappe.db.rollback()
		frappe.clear_messages()
		return frappe.db.get_value(REGISTER_DOCTYPE, {"beep_transaction_id": beep_transaction_id})

	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()
	return doc.name


def build_register(fields):
	doc = frappe.new_doc(REGISTER_DOCTYPE)
	# new_doc fills in the user's default Company and the global default Currency;
	# payments belong to the Tingg Settings Company and are in its currency.
	doc.company = get_tingg_company()
	doc.currency = get_company_currency(doc.company) if doc.company else None
	doc.beep_transaction_id = fields.beep_transaction_id
	doc.payer_transaction_id = fields.payer_transaction_id
	doc.account_number = fields.account_number
	doc.customer = find_customer(fields.account_number)
	doc.customer_name = fields.customer_name
	doc.msisdn = fields.msisdn
	doc.hashed_msisdn = fields.hashed_msisdn
	doc.amount_paid = flt(fields.amount)
	doc.status_description = fields.status_description
	doc.receiver_narration = fields.receiver_narration
	doc.payer_narration = fields.payer_narration
	doc.extra_data = fields.extra_data_text
	doc.payment_date = parse_payment_date(fields.payment_date)
	doc.client_code = fields.client_code
	doc.service_id = fields.service_id
	doc.service_code = fields.service_code
	doc.merchant_payment_ids = fields.merchant_payment_ids
	doc.submit_payment = 1
	return doc


def process_register(register_name):
	# Lock the row so that concurrent retries for the same transaction wait for
	# the first one to finish instead of posting the payment twice.
	frappe.db.get_value(REGISTER_DOCTYPE, register_name, "name", for_update=True)
	doc = frappe.get_doc(REGISTER_DOCTYPE, register_name)

	if doc.docstatus != 0:
		# Already handled: acknowledge again so Tingg stops retrying.
		return respond(doc, STATUS_RECEIVED, "Payment already received")

	if not doc.customer:
		# The customer may have been created since the last attempt.
		doc.customer = find_customer(doc.account_number)

	if not doc.customer:
		doc.save(ignore_permissions=True)

		# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
		frappe.db.commit()
		return respond(doc, STATUS_RECEIVED, "Payment received, pending manual allocation")

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
			doc,
			STATUS_REJECTED,
			"Payment received but could not be posted",
			http_status_code=500,
		)

	# nosemgrep: frappe-semgrep-rules.rules.frappe-manual-commit
	frappe.db.commit()
	return respond(doc, STATUS_RECEIVED, "Payment pushed successfully")


def respond(source, status_code, status_description, http_status_code=200):
	"""Set the acknowledgement sent to Tingg.

	`source` is the parsed fields or the register; both carry the transaction IDs.
	"""
	frappe.clear_messages()
	frappe.response["beepTransactionID"] = source.beep_transaction_id
	frappe.response["payerTransactionID"] = source.payer_transaction_id
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
	"""Tingg sends `paymentDate` in UTC; return it in the system timezone.

	A date with no timezone is taken as UTC. A missing or unreadable date falls
	back to now.
	"""
	try:
		payment_date = get_datetime(value) if value else None
	except Exception:
		payment_date = None

	if not payment_date:
		return now_datetime()

	if payment_date.tzinfo:
		payment_date = payment_date.astimezone(datetime.UTC)

	return convert_utc_to_system_timezone(payment_date).replace(tzinfo=None)
