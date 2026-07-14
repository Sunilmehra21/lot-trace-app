import frappe
from frappe import _

from lot_trace.api.lot import get_lot_trace


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.root_lot:
        frappe.throw(_("Please select a Root Lot"))
    data = get_lot_trace(filters.root_lot)
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
        {"label": _("Stage"), "fieldname": "process_stage", "fieldtype": "Data",
         "options": "Lot Process Stage", "width": 70},
        {"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link",
         "options": "Batch", "width": 170},
        {"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link",
         "options": "Item", "width": 170},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link",
         "options": "Warehouse", "width": 140},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 140},
        {"label": _("Voucher"), "fieldname": "voucher_no", "fieldtype": "Dynamic Link",
         "options": "voucher_type", "width": 160},
        {"label": _("Qty +/-"), "fieldname": "actual_qty", "fieldtype": "Float", "width": 90},
        {"label": _("Balance"), "fieldname": "qty_after_transaction",
         "fieldtype": "Float", "width": 90},
        {"label": _("UOM"), "fieldname": "stock_uom", "width": 60},
    ]
    return columns, data


@frappe.whitelist()
def get_filters():
    return [{"fieldname": "root_lot", "label": "Root Lot", "fieldtype": "Link",
             "options": "Root Lot", "reqd": 1}]
