import frappe

from erpnext.accounts.party import get_party_account
from frappe_mpsa_payments.frappe_mpsa_payments.api.payment_entry import (
    get_outstanding_invoices as _get_outstanding_invoices,
    get_unallocated_payments as _get_unallocated_payments,
)


def get_outstanding_invoices(company, customer=None):
    return _get_outstanding_invoices(company, customer, "Sales Invoice")


def get_unallocated_payments(customer, company, currency):
    return _get_unallocated_payments(customer, company, currency)


def create_and_reconcile_payment_reconciliation(
    outstanding_invoices, customer, company, payment_entries
):
    reconcile_doc = frappe.new_doc("Payment Reconciliation")
    reconcile_doc.party_type = "Customer"
    reconcile_doc.party = customer
    reconcile_doc.company = company
    reconcile_doc.receivable_payable_account = get_party_account(
        "Customer", customer, company
    )
    reconcile_doc.get_unreconciled_entries()

    args = {
        "invoices": [],
        "payments": [],
    }

    for invoice in outstanding_invoices:
        invoice_doc = frappe.get_doc("Sales Invoice", invoice.voucher_no)
        args["invoices"].append(
            {
                "invoice_type": "Sales Invoice",
                "invoice_number": invoice_doc.get("name"),
                "invoice_date": invoice_doc.get("posting_date"),
                "amount": invoice_doc.get("grand_total"),
                "outstanding_amount": invoice_doc.get("outstanding_amount"),
                "currency": invoice_doc.get("currency"),
                "exchange_rate": 0,
            }
        )

    for payment_entry in payment_entries:
        payment_entry_doc = frappe.get_doc("Payment Entry", payment_entry.name)
        args["payments"].append(
            {
                "reference_type": "Payment Entry",
                "reference_name": payment_entry_doc.get("name"),
                "posting_date": payment_entry_doc.get("posting_date"),
                "amount": payment_entry_doc.get("unallocated_amount"),
                "unallocated_amount": payment_entry_doc.get("unallocated_amount"),
                "difference_amount": 0,
                "currency": payment_entry_doc.get("currency"),
                "exchange_rate": 0,
            }
        )

    reconcile_doc.allocate_entries(args)
    reconcile_doc.reconcile()
    frappe.db.commit()
