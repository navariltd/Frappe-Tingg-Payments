import frappe
from frappe.query_builder.functions import Count, Trim

DOCTYPE = "Tingg Payment Register"


def execute():
	"""Clear duplicate Beep Transaction IDs so the unique index can be added.

	For each duplicated ID the earliest submitted register (or the earliest one if
	none is submitted) keeps the ID. The others get "-DUP-" and their register name
	appended to the ID, plus a comment, and the whole list goes into one Error Log
	for the accounts team to review, since those registers may have posted a
	payment twice.
	"""
	if not frappe.db.table_exists(DOCTYPE):
		return

	register = frappe.qb.DocType(DOCTYPE)

	# Blank IDs would collide under the unique index; NULLs do not.
	(
		frappe.qb.update(register)
		.set(register.beep_transaction_id, None)
		.where(Trim(register.beep_transaction_id) == "")
	).run()

	duplicate_ids = (
		frappe.qb.from_(register)
		.select(register.beep_transaction_id)
		.where(register.beep_transaction_id.isnotnull())
		.groupby(register.beep_transaction_id)
		.having(Count("*") > 1)
	).run(pluck=True)
	if not duplicate_ids:
		return

	report = []
	for beep_transaction_id in duplicate_ids:
		registers = frappe.get_all(
			DOCTYPE,
			filters={"beep_transaction_id": beep_transaction_id},
			fields=["name", "docstatus", "payment_entry", "creation"],
		)
		registers.sort(key=lambda r: (r.docstatus != 1, r.creation))
		kept, *duplicates = registers

		report.append(f"Beep Transaction ID {beep_transaction_id}: kept on {kept.name}")
		for register in duplicates:
			new_id = f"{beep_transaction_id}-DUP-{register.name}"
			frappe.db.set_value(
				DOCTYPE,
				register.name,
				"beep_transaction_id",
				new_id,
				update_modified=False,
			)
			frappe.get_doc(
				{
					"doctype": "Comment",
					"comment_type": "Comment",
					"reference_doctype": DOCTYPE,
					"reference_name": register.name,
					"content": (
						f"Duplicate of {kept.name} (Beep Transaction ID {beep_transaction_id}). "
						f"ID changed to {new_id} so it could be made unique. "
						"Check whether its Payment Entry posted the payment twice."
					),
				}
			).insert(ignore_permissions=True)
			report.append(
				f"  duplicate {register.name} (docstatus {register.docstatus}, "
				f"Payment Entry {register.payment_entry or '-'}) -> {new_id}"
			)

	frappe.log_error(
		title="Duplicate Tingg payments found during migration",
		message="\n".join(report),
	)
