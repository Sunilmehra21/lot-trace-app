import frappe
from frappe import _

from lot_trace.api.lot import get_lot_trace

# voucher type -> party field on that doctype
PARTY_FIELD = {
    "Purchase Receipt": "supplier",
    "Purchase Invoice": "supplier",
    "Subcontracting Receipt": "supplier",
    "Stock Entry": "supplier",          # set on Send to Subcontractor entries
    "Delivery Note": "customer",
    "Sales Invoice": "customer",
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.root_lot:
        frappe.throw(_("Please select a Root Lot"))
    data = get_lot_trace(filters.root_lot)
    add_party(data)
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
        {"label": _("Stage"), "fieldname": "process_stage", "fieldtype": "Data",
         "width": 70},
        {"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link",
         "options": "Batch", "width": 170},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
         "options": "Item", "width": 170},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link",
         "options": "Warehouse", "width": 140},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 140},
        {"label": _("Voucher"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link",
         "options": "voucher_type", "width": 160},
        {"label": _("Party"), "fieldname": "party", "fieldtype": "Data", "width": 140},
        {"label": _("Qty +/-"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 90},
        {"label": _("Balance"), "fieldname": "qty_after_transaction",
         "fieldtype": "Float", "width": 90},
        {"label": _("UOM"), "fieldname": "stock_uom", "width": 60},
    ]
    return columns, data


def add_party(data):
    """Attach the supplier/customer of each voucher (cached per voucher)."""
    cache = {}
    for row in data:
        vt = row.get("voucher_type")
        vn = row.get("voucher_no")
        key = (vt, vn)
        if key not in cache:
            field = PARTY_FIELD.get(vt)
            party = None
            if field and vn:
                try:
                    party = frappe.db.get_value(vt, vn, field)
                except Exception:
                    party = None
            cache[key] = party or ""
        row["party"] = cache[key]


@frappe.whitelist()
def get_filters():
    return [{"fieldname": "root_lot", "label": "Root Lot", "fieldtype": "Link",
             "options": "Root Lot", "reqd": 1}]
