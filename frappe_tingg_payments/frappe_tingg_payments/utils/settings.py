import frappe
from frappe import _
from frappe.utils import get_link_to_form


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


def get_tingg_company(settings=None):
	"""The Company the integration posts payments to, as set on Tingg Settings."""
	settings = settings or get_active_tingg_settings()
	return settings.get("company") if settings else None


def validate_mode_of_payment_account(mode_of_payment, company):
	"""Payments are posted to the Mode of Payment's default account for the company."""
	if not (mode_of_payment and company):
		return

	has_account = frappe.db.exists(
		"Mode of Payment Account",
		{
			"parenttype": "Mode of Payment",
			"parent": mode_of_payment,
			"company": company,
			"default_account": ["is", "set"],
		},
	)
	if not has_account:
		frappe.throw(
			_(
				"Mode of Payment {0} has no default account for Company {1}. Add one in its Accounts table."
			).format(get_link_to_form("Mode of Payment", mode_of_payment), frappe.bold(company)),
			title=_("Missing Account"),
		)
