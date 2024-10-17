# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
import frappe.defaults
from frappe.model.document import Document
from frappe import _

from frappe_mpsa_payments.frappe_mpsa_payments.api.payment_entry import (
    create_payment_entry,
)


class TinggPaymentRegister(Document):

    def before_save(self):
        self.get_mode_of_payment()

    def get_mode_of_payment(self):
        self.currency = frappe.defaults.get_global_default("currency")
        register_url_list = frappe.get_all(
            "Tingg Register URL", ["company", "mode_of_payment"]
        )

        if len(register_url_list) > 0:
            self.company = register_url_list[0].company
            self.mode_of_payment = register_url_list[0].mode_of_payment

    def before_submit(self):
        if not self.amount_paid:
            frappe.throw(_("Amount Paid is required"))
        if not self.company:
            frappe.throw(_("Company is required"))
        if not self.customer:
            frappe.throw(_("Customer is required"))
        if not self.mode_of_payment:
            frappe.throw(_("Mode of Payment is required"))
        if self.submit_payment:
            self.payment_entry = self.create_payment_entry()

    def create_payment_entry(self):
        payment_entry = create_payment_entry(
            self.company,
            self.customer,
            self.amount_paid,
            self.currency,
            self.mode_of_payment,
            self.payment_date,
            self.customer,
            self.payment_date,
            None,
            self.submit_payment,
        )

        return payment_entry.name
