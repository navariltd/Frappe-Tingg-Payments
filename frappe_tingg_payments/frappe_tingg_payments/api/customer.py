import frappe
from frappe import _

from erpnext.selling.doctype.customer.customer import (
    get_customer_outstanding,
)


@frappe.whitelist(allow_guest=True)
def get_customer_balance(**kwargs):
    args = frappe._dict(kwargs)

    company = frappe.defaults.get_user_default("company")

    customer = frappe.db.get_value("Customer", args.get("customer_id"))
    if not customer:
        frappe.response["message"] = "Customer does not exist"
        frappe.response["http_status_code"] = 404
    else:
        try:
            customer_outstanding_balance = get_customer_outstanding(customer, company)
            customer_name = frappe.db.get_value("Customer", customer, "customer_name")
            print("CUSTOMER", customer_name)
            frappe.response["message"] = {
                "customer_name": customer_name,
                "outstanding_balance": customer_outstanding_balance,
            }
            frappe.response["http_status_code"] = 200
        except Exception as e:
            frappe.response["message"] = _("Something went wrong")
            frappe.log_error(
                f"An error occurred while fetching the outstanding balance: {e}"
            )
