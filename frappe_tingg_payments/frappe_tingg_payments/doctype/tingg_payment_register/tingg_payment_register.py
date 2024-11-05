# Copyright (c) 2024, Navari Limited and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe import _

from ...utils.helpers import (
    create_payment_entry,
    get_outstanding_invoices,
    get_unallocated_payments,
    create_and_reconcile_payment_reconciliation,
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
            frappe.log_error(frappe.get_traceback(), _("Amount Paid is required"))
        if not self.company:
            frappe.log_error(frappe.get_traceback(), _("Company is required"))
        if not self.customer:
            frappe.log_error(frappe.get_traceback(), _("Customer is required"))
        if not self.mode_of_payment:
            frappe.log_error(frappe.get_traceback(), _("Mode of Payment is required"))

        if (
            self.submit_payment
            and self.amount_paid
            and self.company
            and self.customer
            and self.mode_of_payment
        ):
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

    def on_update(self):
        if self.mode_of_payment:
            self.submit_payment = 1
            self.submit()

    def on_submit(self):
        try:
            outstanding_invoices = get_outstanding_invoices(self.company, self.customer)
            unallocated_payments = get_unallocated_payments(
                self.customer, self.company, self.currency, self.payment_entry
            )

            if outstanding_invoices and unallocated_payments:
                create_and_reconcile_payment_reconciliation(
                    outstanding_invoices=outstanding_invoices,
                    customer=self.customer,
                    company=self.company,
                    payment_entries=unallocated_payments,
                )
        except Exception as e:
            frappe.log_error(frappe.get_traceback(), str(e))
