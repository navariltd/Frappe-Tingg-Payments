### Frappe Tingg Payments

This is a Frappe-based application that integrates with the Tingg API from Cellulant, providing support for automatically receiving and reconciling payments within the system.

### Features

- **Tingg Settings:** Configure Live or Sandbox environments.
- **Tingg Register URL:** Allows configuration of `Callback URL` and `Customer URL`
- **Tingg Payment Register:** Records incoming payment transactions received via the Callback URL.

#### DocTypes

<h4>Tingg Settings</h4>

This DocType allows setup of both live and sandbox environments. Additionally, on save, it creates a `Mode of Payment`, `Payment Gateway` and `Payment Gateway Account`

1. **Payment Gateway Name:** Desired name for the the Payment Gateway.
2. **Environment:** `Live` or `Sandbox`.
3. **Log Balance Lookups:** Whether customer balance lookups are saved as Integration Requests (default `Yes`).

Every request Tingg sends to the Callback URL is saved as an **Integration Request** (service `Tingg`), together with the response sent back and a link to the resulting Tingg Payment Register. The log is written before the payment is processed, so it is kept even if processing fails. Balance lookups to the Customer URL are logged the same way unless **Log Balance Lookups** is `No`. Use the **Request Logs** button on Tingg Settings to open them. How long logs are kept is set in Log Settings (90 days by default).

![tingg_settings2](https://github.com/user-attachments/assets/53e2cd10-9f9f-457b-9f1d-111f993bd8d4)

<h4>Tingg Register URL</h4>

This DocType is responsible for the generation of the Callback URL and Customer URL which are shared with for configuration.

1. **Company:** This is the company associated with the Tingg Register URL.
2. **Mode of Payment:** Identifies the payment mode for better categorization in your accounting or ERP system.
3. **Callback URL:** This is a URL used to receive successful payments remitted to your Tingg account into your ERP when a payment is made.
4. **Customer URL:** This is a URL to query a customer's outstanding balance from your ERP.

![image](https://github.com/user-attachments/assets/17263275-efa4-41ea-825b-0b7550fceb63)

<h4>Tingg Payment Register</h4>

This DocType is responsible for acknowledging and reconciling all payments made to your ERP system.

1. **Customer:** Identity of the customer making the payment.
2. **Customer Name:** Name of the customer.
3. **Company:** Company against which the payment is made.
4. **Mode of Payment:** Payment mode used to make the payment.
5. **Amount Paid:** The total amount transacted.
6. **Currency:** Currency used for the transaction.
7. **Service ID:**
8. **Service Code:**
9. **Client Code:**
10. **Payer Narration:** Information about the payment for instance amount paid and Till Number
11. **Receiver Narration:** Provides information on whether the record has been auto acknowledged.
12. **Status Description:** The response short description.
13. **Merchant Payment IDs:**
14. **Beep Transaction ID:** Cellulant's unique identifier for the transaction being acknowledged. It is unique per register, so a repeated callback for the same transaction is acknowledged again without posting a second payment.
15. **Payer Transaction ID:** The unique identifier tied to the client.
16. **Payment Entry:** The Payment Entry created for this payment. Its Reference No is the Beep Transaction ID.
17. **Submit Payment:** Whether the Payment Entry is submitted (and reconciled against outstanding invoices) or left as a draft.
18. **MSISDN:** Customer's phone number.
19. **Hashed MSISDN:** Hashed version of a customer's phone number.
20. **Account Number:**
21. **Extra Data:** Any extra data, stored as text (JSON when Tingg sends an object).
22. **Payment Date:** Date and time of the payment. The Payment Entry is posted on its date.
23. **Status:** `Pending`, `Unmatched` (no customer matches the account number; set the customer and submit by hand), `Failed` (see Processing Error; a retry from Tingg tries again), `Processed` or `Cancelled`.
24. **Processing Error:** Why the last attempt to post the payment failed.

![payment_register2](https://github.com/user-attachments/assets/5f4d1df5-31ed-4715-beef-054580ffbd02)

### How Reconciliation Works

#### Background: reconciliation in ERPNext

- A submitted **Sales Invoice** debits the customer's receivable account (for example _Debtors_). The amount not yet paid is the invoice's **outstanding amount**.
- A **Payment Entry** of type _Receive_ credits that same receivable account and debits a bank or cash account.
- Posting a payment does not by itself say which invoice it pays. Until it is linked to one, the money sits on the Payment Entry as an **unallocated amount** (a credit on the customer's account).
- **Reconciliation** is the step that links the payment to invoices. ERPNext reduces each invoice's outstanding amount (its status becomes _Partly Paid_ or _Paid_), adds the invoice to the Payment Entry's references, and lowers the unallocated amount. ERPNext's **Payment Reconciliation** tool (_Accounting > Payment Reconciliation_) does this, and this app drives that same tool from code.

#### What happens when Tingg confirms a payment

1. Tingg calls the Callback URL and a **Tingg Payment Register** is created.
2. When the register is submitted, the app creates a **Payment Entry**:
   - type _Receive_, party = the customer
   - paid from the customer's receivable account, into the default account of the register's **Mode of Payment**
   - posting date = the payment date; **Reference No** = the Beep Transaction ID
3. If **Submit Payment** is ticked (it always is for payments from Tingg), the Payment Entry is submitted and reconciliation runs:
   - the app loads the customer's outstanding vouchers in that receivable account, the same rows the Payment Reconciliation tool would show.
   - it allocates the payment to them **oldest first** (by posting date), paying each in full until the money runs out; the last one may be paid in part
   - ERPNext then applies the allocation exactly as if someone had clicked **Reconcile** in the tool.

#### When there is money left over, or nothing to pay

If the payment is larger than everything outstanding, or the customer has nothing outstanding, the remainder stays as an unallocated amount on the Payment Entry. It is still recorded and already reduces the balance returned by the Customer URL. To use it against a later invoice, reconcile it in the Payment Reconciliation tool, or let ERPNext do it on a schedule by enabling **Auto Reconcile Payments** in Accounts Settings.

#### When reconciliation does not run or fails

- **Submit Payment not ticked:** the Payment Entry stays a draft and nothing is reconciled.
- **Unmatched registers** (no customer matches the account number) are not posted at all. Once someone sets the customer and submits the register, the steps above run as normal.
- **Reconciliation errors** (for example, an ERPNext _Auto Reconcile_ job already running for the same customer) undo the reconciliation only. Reconcile it by hand in the Payment Reconciliation tool: choose the company, the customer and the receivable account, click **Get Unreconciled Entries**, allocate, then click **Reconcile**.

### Installation

1. Ensure you have a working Frappe and ERPNext instance.
2. Clone this repository into your Frappe bench apps directory.

```
bench get-app https://github.com/navariltd/Frappe-Tingg-Payments
```

3. Install the app into your site using:

```
bench --site [sitename] install-app frappe_tingg_payments
```

4. Configure "Tingg Settings" and "Tingg Register URL" in the system.

5. Copy "Callback URL" and "Customer URL" to Cellulant for configuration.

### License

agpl-3.0
