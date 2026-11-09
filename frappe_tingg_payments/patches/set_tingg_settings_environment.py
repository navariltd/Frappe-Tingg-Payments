import frappe
from frappe.query_builder.functions import Coalesce


def execute():
	"""Carry the old Sandbox checkbox over to the new Environment select."""
	settings = frappe.qb.DocType("Tingg Settings")
	no_environment = Coalesce(settings.environment, "") == ""

	if frappe.db.has_column("Tingg Settings", "sandbox"):
		(
			frappe.qb.update(settings)
			.set(settings.environment, "Sandbox")
			.where(no_environment & (settings.sandbox == 1))
		).run()

	(frappe.qb.update(settings).set(settings.environment, "Live").where(no_environment)).run()

	(
		frappe.qb.update(settings)
		.set(settings.log_balance_lookups, "Yes")
		.where(Coalesce(settings.log_balance_lookups, "") == "")
	).run()
