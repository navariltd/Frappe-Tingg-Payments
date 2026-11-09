import frappe


def execute():
	"""Fill the new Status field on registers created before it existed."""
	frappe.db.sql(
		"""update `tabTingg Payment Register`
        set status = case
            when docstatus = 1 then 'Processed'
            when docstatus = 2 then 'Cancelled'
            when coalesce(customer, '') = '' then 'Unmatched'
            else 'Pending'
        end
        where coalesce(status, '') = ''"""
	)
