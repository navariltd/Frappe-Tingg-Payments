import frappe


@frappe.whitelist(allow_guest=True)
def confirmation(**kwargs):
    frappe.set_user("Administrator")

    try:
        args = frappe._dict(kwargs)
        doc = frappe.new_doc("Tingg Payment Register")
        doc.customer = args.get("accountNumber")
        doc.customer_name = args.get("customerName")
        doc.msisdn = args.get("MSISDN")
        doc.hashed_msisdn = args.get("hashed_msisdn")
        doc.amount_paid = float(args.get("amountPaid"))
        doc.beep_transaction_id = args.get("beepTransactionID")
        doc.payer_transaction_id = args.get("payerTransactionID")
        doc.status_description = args.get("statusDescription")
        doc.receiver_narration = args.get("receiverNarration")
        doc.payer_narration = args.get("payerNarration")

        if args.get("extraData") and (type(args("extraDate") != str)):
            doc.extra_data = args.get("extraData")

        doc.payment_date = args.get("paymentDate")
        doc.client_code = args.get("clientCode")
        doc.service_id = int(float(args.get("serviceID")))
        doc.service_code = args.get("serviceCode")
        doc.merchant_payment_ids = args.get("merchantPaymentIDs")
        doc.save()
    except Exception as e:
        frappe.log_error(str(e))
