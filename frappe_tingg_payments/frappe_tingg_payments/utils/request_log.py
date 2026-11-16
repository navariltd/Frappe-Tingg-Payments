"""Record incoming Tingg requests as Integration Requests.

Each request is logged before the endpoint runs and committed straight away, so the
log survives even if the endpoint fails and rolls back. Once the endpoint finishes,
the log is updated with the response sent back to Tingg.

Passwords in the request (e.g. Tingg's callback credentials) are masked before
they are saved.

Logging never blocks a request: if writing the log fails, the failure goes to the
Error Log and the endpoint runs as normal.
"""

import functools
import json

import frappe
from frappe import _

SERVICE_NAME = "Tingg"

REDACTED = "*****"
SECRET_KEYS = {"password"}


# Internal keys Frappe keeps on the response that are not part of what Tingg receives.
INTERNAL_RESPONSE_KEYS = {
	"docs",
	"_server_messages",
	"_debug_messages",
	"exc",
	"exc_type",
}


def log_tingg_request(description, request_id_key, is_enabled=None):
	"""Decorator for a Tingg endpoint. Put it below `@frappe.whitelist`.

	Args:
	    description: Shown as the Integration Request's description.
	    request_id_key: Where the request's identifier is: either a top-level key, or a
	        function that takes a dict and returns the identifier (for nested bodies).
	        It is looked up in the request body first and in the response if the
	        body lacks it.
	    is_enabled: Optional callable; when it returns False nothing is logged.
	"""

	def decorator(fn):
		@functools.wraps(fn)
		def wrapper(*args, **kwargs):
			if is_enabled and not is_enabled():
				return fn(*args, **kwargs)

			frappe.flags.tingg_request_reference = None
			log_name = start_request_log(description, kwargs, request_id_key)

			try:
				result = fn(*args, **kwargs)
			except Exception:
				frappe.db.rollback()
				finish_request_log(log_name, request_id_key, error=frappe.get_traceback())
				raise

			finish_request_log(log_name, request_id_key)
			return result

		return wrapper

	return decorator


def set_request_reference(doctype, name):
	"""Link the current request's log to a document, e.g. the payment register."""
	frappe.flags.tingg_request_reference = (doctype, name)


def start_request_log(description, kwargs, request_id_key):
	try:
		arguments = {k: v for k, v in kwargs.items() if k != "cmd"}
		request = getattr(frappe.local, "request", None)
		raw_body = None if arguments else get_raw_body(request)
		body = arguments or load_json(raw_body)

		log = frappe.get_doc(
			{
				"doctype": "Integration Request",
				"integration_request_service": SERVICE_NAME,
				"request_description": description,
				"is_remote_request": 0,
				"status": "Queued",
				"request_id": get_request_id(body, request_id_key),
				"url": request.url if request else None,
				"request_headers": request.headers if request else None,
				"data": to_json(redact(body)) if isinstance(body, dict) else raw_body,
			}
		)
		log.insert(ignore_permissions=True)
		frappe.db.commit()
		return log.name
	except Exception:
		frappe.db.rollback()
		frappe.log_error(title=_("Could not log Tingg request"), message=frappe.get_traceback())
		frappe.db.commit()
		return None


def finish_request_log(log_name, request_id_key, error=None):
	if not log_name:
		return

	try:
		response = {k: v for k, v in frappe.response.items() if k not in INTERNAL_RESPONSE_KEYS}
		http_status_code = response.get("http_status_code") or (500 if error else 200)
		failed = bool(error) or http_status_code >= 400

		values = {
			"status": "Failed" if failed else "Completed",
			"output": to_json(response),
		}
		if failed:
			values["error"] = error or stringify(response.get("statusDescription") or response.get("message"))

		request_id = get_request_id(response, request_id_key)
		if request_id:
			values["request_id"] = request_id

		reference = frappe.flags.tingg_request_reference
		if reference:
			values["reference_doctype"], values["reference_docname"] = reference

		frappe.db.set_value("Integration Request", log_name, values, update_modified=True)
		frappe.db.commit()
	except Exception:
		frappe.db.rollback()
		frappe.log_error(
			title=_("Could not update Tingg request log {0}").format(log_name),
			message=frappe.get_traceback(),
		)
		frappe.db.commit()


def get_request_id(data, request_id_key):
	if not isinstance(data, dict):
		return None
	value = request_id_key(data) if callable(request_id_key) else data.get(request_id_key)
	return stringify(value) if value not in (None, "") else None


def get_raw_body(request):
	if not request:
		return None
	return request.get_data(as_text=True) or None


def to_json(value):
	return json.dumps(value, indent=2, default=str)


def stringify(value):
	if value is None:
		return None
	if isinstance(value, (dict | list)):
		return to_json(value)
	return str(value)


def load_json(value):
	"""Parse a JSON string, also unwrapping a JSON document that was encoded twice.

	Returns None if the string is not valid JSON.
	"""
	for _attempt in range(2):
		if not isinstance(value, str):
			break
		try:
			value = json.loads(value)
		except ValueError:
			return None
	return value


def redact(value):
	"""A copy of `value` with every password masked, including inside JSON strings."""
	if isinstance(value, dict):
		return {k: REDACTED if str(k).lower() in SECRET_KEYS and v else redact(v) for k, v in value.items()}
	if isinstance(value, list):
		return [redact(v) for v in value]
	if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
		parsed = load_json(value)
		if isinstance(parsed, (dict | list)):
			redacted = redact(parsed)
			# Keep the string as received unless something in it had to be masked.
			return to_json(redacted) if redacted != parsed else value
	return value
