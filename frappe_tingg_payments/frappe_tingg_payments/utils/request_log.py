"""Record incoming Tingg requests as Integration Requests.

Each request is logged before the endpoint runs and committed straight away, so the
log survives even if the endpoint fails and rolls back. Once the endpoint finishes,
the log is updated with the response sent back to Tingg.

Logging never blocks a request: if writing the log fails, the failure goes to the
Error Log and the endpoint runs as normal.
"""

import functools
import json

import frappe
from frappe import _

SERVICE_NAME = "Tingg"


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
	    request_id_key: Key holding the request's identifier. It is looked up in the
	        request arguments first and in the response if the arguments lack it.
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

		log = frappe.get_doc(
			{
				"doctype": "Integration Request",
				"integration_request_service": SERVICE_NAME,
				"request_description": description,
				"is_remote_request": 0,
				"status": "Queued",
				"request_id": stringify(arguments.get(request_id_key)),
				"url": request.url if request else None,
				"request_headers": request.headers if request else None,
				"data": to_json(arguments) if arguments else get_raw_body(request),
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

		if response.get(request_id_key):
			values["request_id"] = stringify(response.get(request_id_key))

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
