import frappe


def get_active_register_url():
	"""The Tingg Register URL the integration posts payments with.

	TODO: pick the one matching the incoming service once multiple companies are supported.
	"""
	register_urls = frappe.get_all(
		"Tingg Register URL",
		fields=["company", "mode_of_payment", "tingg_settings"],
		limit=1,
	)
	return register_urls[0] if register_urls else None


def get_active_tingg_settings():
	register_url = get_active_register_url()
	name = register_url.tingg_settings if register_url else frappe.db.get_value("Tingg Settings", {}, "name")
	return frappe.get_cached_doc("Tingg Settings", name) if name else None


def balance_lookup_logging_enabled():
	"""Balance lookups are logged unless the active Tingg Settings turn it off."""
	settings = get_active_tingg_settings()
	return not settings or settings.get("log_balance_lookups") != "No"
