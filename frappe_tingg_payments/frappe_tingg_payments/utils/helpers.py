import frappe, erpnext

from erpnext.accounts.party import get_party_account
from erpnext.accounts.utils import get_account_currency
from erpnext.accounts.doctype.journal_entry.journal_entry import (
    get_default_bank_cash_account,
)
from erpnext.accounts.utils import QueryPaymentLedger
from erpnext.accounts.doctype.bank_account.bank_account import get_party_bank_account
from erpnext.setup.utils import get_exchange_rate

from frappe import _, qb
from frappe.utils import nowdate, flt, getdate


def create_payment_entry(
    company,
    customer,
    amount,
    currency,
    mode_of_payment,
    reference_date=None,
    reference_no=None,
    posting_date=None,
    cost_center=None,
    submit=0,
):
    """
    Create a payment entry for a given customer and company.

    Args:
            company (str): Company for which the payment entry is being created.
            customer (str): Customer for whom the payment entry is being created.
            amount (float): Amount of the payment.
            currency (str): Currency of the payment.
            mode_of_payment (str): Mode of payment for the transaction.
            reference_date (str, optional): Reference date for the payment entry. Defaults to None.
            reference_no (str, optional): Reference number for the payment entry. Defaults to None.
            posting_date (str, optional): Posting date for the payment entry. Defaults to None.
            cost_center (str, optional): Cost center for the payment entry. Defaults to None.
            submit (int, optional): Whether to submit the payment entry immediately. Defaults to 0.

    Returns:
            PaymentEntry: Newly created payment entry document.
    """
    # TODO : need to have a better way to handle currency
    date = nowdate() if not posting_date else posting_date
    party_type = "Customer"
    party_account = get_party_account(party_type, customer, company)
    party_account_currency = get_account_currency(party_account)
    if party_account_currency != currency:
        frappe.throw(
            _(
                "Currency is not correct, party account currency is {party_account_currency} and transaction currency is {currency}"
            ).format(party_account_currency=party_account_currency, currency=currency)
        )
    payment_type = "Receive"

    bank = get_bank_cash_account(company, mode_of_payment)
    company_currency = frappe.get_value("Company", company, "default_currency")
    conversion_rate = get_exchange_rate(currency, company_currency, date, "for_selling")
    paid_amount, received_amount = set_paid_amount_and_received_amount(
        party_account_currency, bank, amount, payment_type, None, conversion_rate
    )

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = payment_type
    pe.company = company
    pe.cost_center = cost_center or erpnext.get_default_cost_center(company)
    pe.posting_date = date
    pe.mode_of_payment = mode_of_payment
    pe.party_type = party_type
    pe.party = customer

    pe.paid_from = party_account if payment_type == "Receive" else bank.account
    pe.paid_to = party_account if payment_type == "Pay" else bank.account
    pe.paid_from_account_currency = (
        party_account_currency if payment_type == "Receive" else bank.account_currency
    )
    pe.paid_to_account_currency = (
        party_account_currency if payment_type == "Pay" else bank.account_currency
    )
    pe.paid_amount = paid_amount
    pe.received_amount = received_amount
    pe.letter_head = frappe.get_value("Company", company, "default_letter_head")
    pe.reference_date = reference_date
    pe.reference_no = reference_no
    if pe.party_type in ["Customer", "Supplier"]:
        bank_account = get_party_bank_account(pe.party_type, pe.party)
        pe.set("bank_account", bank_account)
        pe.set_bank_account_data()

    pe.setup_party_account_field()
    pe.set_missing_values()

    if party_account and bank:
        pe.set_amounts()
    if submit:
        pe.docstatus = 1
    pe.insert(ignore_permissions=True)
    return pe


def get_bank_cash_account(company, mode_of_payment, bank_account=None):
    """
    Retrieve the default bank or cash account based on the company and mode of payment.

    Args:
            company (str): Company for which the account is being retrieved.
            mode_of_payment (str): Mode of payment for the transaction.
            bank_account (str, optional): Specific bank account to retrieve. Defaults to None.

    Returns:
            BankAccount: Default bank or cash account.
    """
    bank = get_default_bank_cash_account(
        company, "Bank", mode_of_payment=mode_of_payment, account=bank_account
    )

    if not bank:
        bank = get_default_bank_cash_account(
            company, "Cash", mode_of_payment=mode_of_payment, account=bank_account
        )

    return bank


def set_paid_amount_and_received_amount(
    party_account_currency,
    bank,
    outstanding_amount,
    payment_type,
    bank_amount,
    conversion_rate,
):
    """
    Set the paid amount and received amount based on currency and conversion rate.

    Args:
            party_account_currency (str): Currency of the party account.
            bank (BankAccount): Bank account used for the transaction.
            outstanding_amount (float): Outstanding amount to be paid/received.
            payment_type (str): Type of payment (Receive/Pay).
            bank_amount (float): Amount in the bank account currency (if available).
            conversion_rate (float): Conversion rate between currencies.

    Returns:
            float: Paid amount.
            float: Received amount.
    """
    paid_amount = received_amount = 0
    if party_account_currency == bank["account_currency"]:
        paid_amount = received_amount = abs(outstanding_amount)
    elif payment_type == "Receive":
        paid_amount = abs(outstanding_amount)
        if bank_amount:
            received_amount = bank_amount
        else:
            received_amount = paid_amount * conversion_rate

    else:
        received_amount = abs(outstanding_amount)
        if bank_amount:
            paid_amount = bank_amount
        else:
            # if party account currency and bank currency is different then populate paid amount as well
            paid_amount = received_amount * conversion_rate

    return paid_amount, received_amount


def get_outstanding_invoices(
    company,
    customer,
    invoice_type="Sales Invoice",
    common_filter=None,
    posting_date=None,
    min_outstanding=None,
    max_outstanding=None,
    accounting_dimensions=None,
    vouchers=None,
    limit=None,
    voucher_no=None,
):

    account = (get_party_account("Customer", customer, company),)
    ple = qb.DocType("Payment Ledger Entry")
    outstanding_invoices = []
    precision = frappe.get_precision(invoice_type, "outstanding_amount") or 2

    if account:
        root_type, account_type = frappe.get_cached_value(
            "Account", account[0], ["root_type", "account_type"]
        )
        party_account_type = "Receivable" if root_type == "Asset" else "Payable"
        party_account_type = account_type or party_account_type
    else:
        party_account_type = erpnext.get_party_account_type("Customer")

    common_filter = common_filter or []
    common_filter.append(ple.account_type == party_account_type)
    common_filter.append(ple.account.isin(account))
    common_filter.append(ple.party_type == "Customer")
    common_filter.append(ple.party == customer)

    ple_query = QueryPaymentLedger()
    invoice_list = ple_query.get_voucher_outstandings(
        vouchers=vouchers,
        common_filter=common_filter,
        posting_date=posting_date,
        min_outstanding=min_outstanding,
        max_outstanding=max_outstanding,
        get_invoices=True,
        accounting_dimensions=accounting_dimensions or [],
        limit=limit,
        voucher_no=voucher_no,
    )

    for d in invoice_list:
        payment_amount = (
            d.invoice_amount_in_account_currency - d.outstanding_in_account_currency
        )
        outstanding_amount = d.outstanding_in_account_currency
        if outstanding_amount > 0.5 / (10**precision):
            if (
                min_outstanding
                and max_outstanding
                and (
                    outstanding_amount < min_outstanding
                    or outstanding_amount > max_outstanding
                )
            ):
                continue

            if d.voucher_type != "Purchase Invoice":
                outstanding_invoices.append(
                    frappe._dict(
                        {
                            "voucher_no": d.voucher_no,
                            "voucher_type": d.voucher_type,
                            "posting_date": d.posting_date,
                            "invoice_amount": flt(d.invoice_amount_in_account_currency),
                            "payment_amount": payment_amount,
                            "outstanding_amount": outstanding_amount,
                            "due_date": d.due_date,
                            "currency": d.currency,
                            "account": d.account,
                        }
                    )
                )

    outstanding_invoices = sorted(
        outstanding_invoices, key=lambda k: k["due_date"] or getdate(nowdate())
    )
    return outstanding_invoices


def get_unallocated_payments(customer, company, currency, payment_name):
    filters = {
        "name": payment_name,
        "party": customer,
        "company": company,
        "docstatus": 1,
        "party_type": "Customer",
        "payment_type": "Receive",
        "unallocated_amount": [">", 0],
        "paid_from_account_currency": currency,
    }

    unallocated_payment = frappe.db.get_value(
        "Payment Entry",
        filters,
        [
            "name",
            "paid_amount",
            "party_name as customer_name",
            "received_amount",
            "posting_date",
            "unallocated_amount",
            "mode_of_payment",
            "paid_from_account_currency as currency",
        ],
        as_dict=True,
    )
    return [unallocated_payment]


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
