### Frappe Tingg Payments

This is a Frappe-based application that integrates with the Tingg API from Cellulant, providing support for automatically receiving and reconciling payments within the system.

### Features

  - **Tingg Settings:** Configure Live or Sandbox environments.
  - **Tingg Register URL:** Allows configuration of ```Callback URL``` and ```Customer URL```
  - **Tingg Payment Register:** Records incoming payment transactions received via the Callback URL.

#### DocTypes

<h4>Tingg Settings</h4>

This DocType allows setup of both live and sandbox environments. Additionally, on save, it creates a `Mode of Payment`, `Payment Gateway` and `Payment Gateway Account`

1. **Payment Gateway Name:** Desired name for the the Payment Gateway.
2. **Sandbox:** Tick if the settings are for the sandbox environment.
   
![tingg_settings2](https://github.com/user-attachments/assets/53e2cd10-9f9f-457b-9f1d-111f993bd8d4)

<h4>Tingg Register URL</h4>

This DocType is responsible for the generation of the Callback URL and Customer URL which are shared with for configuration.

1. **Company:** This is the company associated with the Tingg Register URL.
2. **Mode of Payment:** Identifies the payment mode for better categorization in your accounting or ERP system.
3. **Callback URL:** This is a URL used to receive successful payments remitted to your Tingg account into your ERP when a payment is made.
4. **Customer URL:** This is a URL to query a customer's outstanding balance from your ERP.

![tingg_register_url2](https://github.com/user-attachments/assets/6d6a3c1e-6f49-41be-93ff-fcb2cea20dda)

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
14. **Beep Transaction ID:** Cellulant's unqique identifier for the transaction being acknowledged.
15. **Payer Transaction ID:** The unique identifier tied to the client.
16. **Payment Entry:** This is a record in the ERP indicating that a payment has been made for an invoice
17. **Submit Payment:** This is a boolean value that indicates whether to submit the payment or not.
18. **MSISDN:** Customer's phone number.
19. **Hashed MSISDN:** Hashed version of a customer's phone number.
20. **Account Number:**
21. **Extra Data:** Any extra data usually in JSON format.

![payment_register2](https://github.com/user-attachments/assets/5f4d1df5-31ed-4715-beef-054580ffbd02)

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
