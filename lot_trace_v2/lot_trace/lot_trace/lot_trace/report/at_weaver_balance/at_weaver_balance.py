import frappe
from frappe import _

from lot_trace.api.lot import at_weaver_balance


def execute(filters=None):
    filters = frappe._dict(filters or {})
    data = at_weaver_balance(weaver=filters.weaver, root_lot=filters.root_lot)
    columns = [
        {"label": _("Root Lot"), "fieldname": "root_lot", "fieldtype": "Link",
         "options": "Root Lot", "width": 160},
        {"label": _("Weaver"), "fieldname": "weaver", "fieldtype": "Link",
         "options": "Supplier", "width": 160},
        {"label": _("Dyed Yarn Sold (Kg)"), "fieldname": "dyed_yarn_sold_kg",
         "fieldtype": "Float", "width": 140},
        {"label": _("Consumed per BOM (Kg)"), "fieldname": "consumed_equiv_kg",
         "fieldtype": "Float", "width": 160},
        {"label": _("Balance at Weaver (Kg)"), "fieldname": "balance_at_weaver_kg",
         "fieldtype": "Float", "width": 160},
    ]
    return columns, data
