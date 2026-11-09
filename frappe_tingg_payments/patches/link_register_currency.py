import frappe

DOCTYPE = "Tingg Payment Register"


def execute():
	"""Make existing Currency values valid now that the field links to Currency.

	- A value that matches a Currency apart from case or spacing is corrected.
	- A draft with an unknown currency gets its company's default currency (or the
	  global default) so it can still be saved and submitted.
	- A submitted register with an unknown currency is left unchanged.
	Anything that could not be matched is listed in one Error Log.
	"""
	report = []
	for row in frappe.get_all(DOCTYPE, fields=["name", "currency", "company", "docstatus"]):
		value = (row.currency or "").strip()
		if not value:
			# Blank drafts get a currency on their next save.
			continue

		match = frappe.db.get_value("Currency", value)
		if match:
			if match != row.currency:
				frappe.db.set_value(DOCTYPE, row.name, "currency", match, update_modified=False)
			continue

		if row.docstatus == 0:
			fallback = (
				row.company and frappe.get_cached_value("Company", row.company, "default_currency")
			) or frappe.defaults.get_global_default("currency")
			frappe.db.set_value(DOCTYPE, row.name, "currency", fallback, update_modified=False)
			report.append(f"{row.name} (draft): unknown currency {row.currency!r} replaced with {fallback!r}")
		else:
			report.append(f"{row.name} (submitted): unknown currency {row.currency!r} left unchanged")

	if report:
		frappe.log_error(
			title="Tingg Payment Register currencies not found during migration",
			message="\n".join(report),
		)
