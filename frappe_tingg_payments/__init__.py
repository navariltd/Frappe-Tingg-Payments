
import frappe
from frappe.utils.user import is_website_user

__version__ = "0.0.1"


def check_app_permission():
    """Show Tingg Payments only to authorized Desk users."""
    if is_website_user():
        return False

    return any(
        frappe.has_permission(doctype, "read")
        for doctype in (
            "Tingg Payment Register",
            "Tingg Settings",
            "Tingg Register URL",
        )
    )
