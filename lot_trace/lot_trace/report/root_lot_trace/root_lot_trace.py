import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.api.lot import get_lot_trace

PARTY_FIELD = {
    "Purchase Receipt": "supplier",
    "Purchase Invoice": "supplier",
    "Subcontracting Receipt": "supplier",
    "Stock Entry": "supplier",
    "Delivery Note": "customer",
    "Sales Invoice": "customer",
}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.root_lot:
        frappe.throw(_("Please select a Root Lot"))

    raw = get_lot_trace(filters.root_lot)
    if not raw:
        return get_columns(), []

    # ── Per-batch running balance (B5 fix) ───────────────────────────
    # sort by date/time/name (same order as get_lot_trace returns)
    # accumulate balance PER BATCH, not per item-warehouse.
    batch_balance = {}   # {batch_no: running_balance}
    rows = []
    for sle in raw:
        bn = sle.get("batch_no") or ""
        batch_balance[bn] = round(
            flt(batch_balance.get(bn, 0)) + flt(sle.get("actual_qty", 0)), 3)

        party = add_party(sle)
        rows.append({
            "date": sle.get("posting_date"),
            "stage": sle.get("process_stage"),
            "batch": bn,
            "item": sle.get("item_code"),
            "warehouse": sle.get("warehouse"),
            "voucher_type": sle.get("voucher_type"),
            "voucher": sle.get("voucher_no"),
            "party": party,
            "qty": flt(sle.get("actual_qty")),
            "balance": batch_balance[bn],
            "uom": sle.get("stock_uom"),
        })

    columns = get_columns()
    return columns, rows


def add_party(sle):
    vtype = sle.get("voucher_type")
    vno = sle.get("voucher_no")
    field = PARTY_FIELD.get(vtype)
    if not field or not vno:
        return ""
    try:
        return frappe.db.get_value(vtype, vno, field) or ""
    except Exception:
        return ""


def get_columns():
    return [
        {"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 90},
        {"label": _("Stage"), "fieldname": "stage", "fieldtype": "Link",
         "options": "Lot Process Stage", "width": 70},
        {"label": _("Batch"), "fieldname": "batch", "fieldtype": "Link",
         "options": "Batch", "width": 200},
        {"label": _("Item"), "fieldname": "item", "fieldtype": "Link",
         "options": "Item", "width": 180},
        {"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link",
         "options": "Warehouse", "width": 140},
        {"label": _("Voucher Type"), "fieldname": "voucher_type", "width": 130},
        {"label": _("Voucher"), "fieldname": "voucher", "fieldtype": "Dynamic Link",
         "options": "voucher_type", "width": 160},
        {"label": _("Party"), "fieldname": "party", "width": 140},
        {"label": _("Qty +/−"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
        {"label": _("Balance"), "fieldname": "balance", "fieldtype": "Float", "width": 100},
        {"label": _("UOM"), "fieldname": "uom", "width": 60},
    ]
