import frappe
from erpnext.selling.doctype.customer.customer import (
	get_customer_outstanding,
)
from frappe import _

from ..utils.request_log import log_tingg_request, set_request_reference
from ..utils.settings import balance_lookup_logging_enabled


# nosemgrep: frappe-semgrep-rules.rules.security.guest-whitelisted-method
@frappe.whitelist(allow_guest=True)
@log_tingg_request(
	"Customer Balance Lookup",
	request_id_key="customer_id",
	is_enabled=balance_lookup_logging_enabled,
)
def get_customer_balance(**kwargs):
	args = frappe._dict(kwargs)

	company = frappe.defaults.get_user_default("company")

	customer = frappe.db.get_value("Customer", args.get("customer_id"))
	if customer:
		set_request_reference("Customer", customer)

	if not customer:
		frappe.response["message"] = "Customer does not exist"
		frappe.response["http_status_code"] = 404
	else:
		try:
			# Only invoiced and delivered amounts; orders not yet delivered are excluded.
			customer_outstanding_balance = get_customer_outstanding(
				customer, company, ignore_outstanding_sales_order=True
			)
			customer_name = frappe.db.get_value("Customer", customer, "customer_name")
			frappe.response["message"] = {
				"customer_name": customer_name,
				"outstanding_balance": customer_outstanding_balance,
			}
			frappe.response["http_status_code"] = 200
		except Exception:
			frappe.response["message"] = _("Something went wrong")
			frappe.response["http_status_code"] = 500
			frappe.log_error(
				title=_("Tingg customer balance lookup failed for {0}").format(customer),
				message=frappe.get_traceback(),
				reference_doctype="Customer",
				reference_name=customer,
				# GET requests are rolled back at the end, so queue the log instead.
				defer_insert=True,
			)
