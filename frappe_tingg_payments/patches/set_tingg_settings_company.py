import frappe


def execute():
	"""Give each Tingg Settings a Company now that the Company is set there.

	It takes the Company of its Tingg Register URL, or the only Company on the site.
	Settings that could not be given one are listed in an Error Log.
	"""
	companies = frappe.get_all("Company", pluck="name", limit=2)
	only_company = companies[0] if len(companies) == 1 else None

	missing = []
	for name in frappe.get_all("Tingg Settings", filters={"company": ["is", "not set"]}, pluck="name"):
		company = (
			frappe.db.get_value("Tingg Register URL", {"tingg_settings": name}, "company") or only_company
		)
		if company:
			frappe.db.set_value("Tingg Settings", name, "company", company, update_modified=False)
		else:
			missing.append(name)

	if missing:
		frappe.log_error(
			title="Tingg Settings without a Company after migration",
			message="Set the Company on these Tingg Settings: " + ", ".join(missing),
		)
