import frappe


@frappe.whitelist(allow_guest=True)
def confirmation(**kwargs):
    frappe.set_user("Administrator")

    try:
        args = frappe._dict(kwargs)
        doc = frappe.new_doc("Tingg Payment Register")
        doc.customer = args.get("customerName")
        doc.msisdn = args.get("MSISDN")
        doc.service_code = args.get("serviceCode")
        doc.amount_paid = float(args.get("amountPaid"))
        doc.invoice_number = args.get("invoiceNumber")
        doc.receipt_number = args.get("receiptNumber")
        doc.payer_transaction_id = args.get("payerTransactionID")
        doc.payment_id = args.get("paymentID")
        doc.account_number = args.get("accountNumber")
        doc.receiver_narration = args.get("receiverNarration")
        doc.payer_narration = args.get("payerNarration")

        if args.get("extraData") and (type(args("extraDate") != str)):
            doc.extra_data = args.get("extraData")
        # doc.mode_of_payment = args.get("paymentMode")
        doc.payment_ack_date = args.get("paymentAckDate")
        doc.payment_date = args.get("paymentDate")
        doc.iso_code = args.get("ISOCode")
        doc.client_code = args.get("clientCode")
        doc.status_first_send = args.get("statusFirtSend")
        doc.next_send_time = args.get("nextSendTime")
        doc.service_id = int(float(args.get("serviceID")))
        doc.last_send = args.get("lastSend")
        doc.overall_status = args.get("overallStatus")
        doc.hub_country = args.get("hubCountry")
        doc.hub_id = args.get("hubID")
        doc.number_of_sends = args.get("numberOfSends")
        doc.save()
    except Exception as e:
        frappe.log_error(str(e))
