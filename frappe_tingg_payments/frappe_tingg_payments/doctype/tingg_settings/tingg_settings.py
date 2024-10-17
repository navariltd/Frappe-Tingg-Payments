# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import call_hook_method
from payments.utils import create_payment_gateway

from payments.payment_gateways.doctype.mpesa_settings.mpesa_settings import (
    create_mode_of_payment,
)


class TinggSettings(Document):
    """Tingg Settings Doctype"""

    def on_update(self) -> None:
        """On Update Hook"""
        create_payment_gateway(
            "Tingg-" + self.payment_gateway_name,
            settings="Tingg Settings",
            controller=self.payment_gateway_name,
        )

        call_hook_method(
            "payment_gateway_enabled",
            gateway="Tingg-" + self.payment_gateway_name,
            payment_channel="Phone",
        )

        create_mode_of_payment(
            "Tingg-" + self.payment_gateway_name, payment_type="Phone"
        )

        frappe.db.commit()
