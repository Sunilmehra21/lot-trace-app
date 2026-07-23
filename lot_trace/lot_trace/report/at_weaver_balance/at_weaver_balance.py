import frappe
from frappe import _

from lot_trace.api.lot import at_weaver_balance


def execute(filters=None):
	filters = frappe._dict(filters or {})

	data = at_weaver_balance(
		weaver=filters.get("weaver") or None,
		root_lot=filters.get("root_lot") or None,
	)

	columns = [
		{"label": _("Root Lot"), "fieldname": "root_lot", "fieldtype": "Link",
		 "options": "Root Lot", "width": 160},
		{"label": _("Weaver"), "fieldname": "weaver", "fieldtype": "Link",
		 "options": "Customer", "width": 180},
		{"label": _("Dyed Yarn Sold (Kg)"), "fieldname": "dyed_yarn_sold_kg",
		 "fieldtype": "Float", "width": 140},
		{"label": _("Weaved Pcs Received"), "fieldname": "weaved_pcs_received",
		 "fieldtype": "Float", "width": 145},
		{"label": _("Consumed per BOM (Kg)"), "fieldname": "consumed_equiv_kg",
		 "fieldtype": "Float", "width": 155},
		{"label": _("Balance at Weaver (Kg)"), "fieldname": "balance_at_weaver_kg",
		 "fieldtype": "Float", "width": 155},
	]
	return columns, data
