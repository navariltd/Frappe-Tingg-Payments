# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import get_request_site_address


class TinggRegisterURL(Document):
    """Tingg Register URL Doctype"""

    def validate(self):
        # TODO handle sandbox and live environments
        # Get current site address
        site_url = get_request_site_address(True)
        callback_url = (
            site_url
            + "/api/method/frappe_tingg_payments.frappe_tingg_payments.api.callback.confirmation"
        )

        customer_url = (
            site_url
            + "/api/method/frappe_tingg_payments.frappe_tingg_payments.api.customer.get_customer_balance"
        )

        if not self.callback_url:
            self.callback_url = callback_url

        if not self.customer_url:
            self.customer_url = customer_url
