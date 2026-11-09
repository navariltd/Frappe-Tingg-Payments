// Copyright (c) 2024, Navari Limited and contributors
// For license information, please see license.txt

frappe.ui.form.on("Tingg Settings", {
	refresh(frm) {
		if (frm.is_new() || !frappe.model.can_read("Integration Request")) return;

		frm.add_custom_button(__("Request Logs"), () => {
			frappe.set_route("List", "Integration Request", {
				integration_request_service: "Tingg",
			});
		});
	},
});
