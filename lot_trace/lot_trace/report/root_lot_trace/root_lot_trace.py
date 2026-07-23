# -*- coding: utf-8 -*-
# Root Lot Trace report: every stock movement of every batch of a lot,
# stage by stage. Read-only SLE (requirement #4).

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "root_lot", "label": _("Root Lot"),
         "fieldtype": "Link", "options": "Root Lot", "width": 140},
        {"fieldname": "process_stage", "label": _("Stage"),
         "fieldtype": "Link", "options": "Lot Process Stage", "width": 70},
        {"fieldname": "batch_no", "label": _("Batch"),
         "fieldtype": "Link", "options": "Batch", "width": 190},
        {"fieldname": "item_code", "label": _("Item"),
         "fieldtype": "Link", "options": "Item", "width": 150},
        {"fieldname": "posting_date", "label": _("Date"),
         "fieldtype": "Date", "width": 100},
        {"fieldname": "voucher_type", "label": _("Voucher Type"),
         "fieldtype": "Data", "width": 140},
        {"fieldname": "voucher_no", "label": _("Voucher"),
         "fieldtype": "Dynamic Link", "options": "voucher_type", "width": 170},
        {"fieldname": "party", "label": _("Party"),
         "fieldtype": "Data", "width": 140},
        {"fieldname": "warehouse", "label": _("Warehouse"),
         "fieldtype": "Link", "options": "Warehouse", "width": 150},
        {"fieldname": "qty", "label": _("Qty"),
         "fieldtype": "Float", "width": 100},
        {"fieldname": "uom", "label": _("UOM"),
         "fieldtype": "Data", "width": 70},
        {"fieldname": "running_balance", "label": _("Batch Balance"),
         "fieldtype": "Float", "width": 110},
    ]


# Voucher type -> party fieldname, and whether that party is a supplier
# (inbound-side document) or a customer (outbound-side document).
SUPPLIER_VOUCHERS = {
    "Purchase Receipt": "supplier",
    "Purchase Invoice": "supplier",
    "Subcontracting Receipt": "supplier",
}
CUSTOMER_VOUCHERS = {
    "Delivery Note": "customer",
    "Sales Invoice": "customer",
}


def _party_map(voucher_type, voucher_nos):
    """Bulk-fetch supplier/customer for a set of vouchers of one type."""
    voucher_nos = [v for v in set(voucher_nos) if v]
    if not voucher_nos:
        return {}
    fieldname = SUPPLIER_VOUCHERS.get(voucher_type) or CUSTOMER_VOUCHERS.get(voucher_type)
    if not fieldname or not frappe.db.has_column(voucher_type, fieldname):
        return {}
    rows = frappe.db.get_all(
        voucher_type, filters={"name": ["in", voucher_nos]},
        fields=["name", fieldname])
    return {r.name: r.get(fieldname) for r in rows}


def get_data(filters):
    conditions = ["b.root_lot IS NOT NULL", "b.root_lot != ''",
                  "sle.is_cancelled = 0"]
    params = {}

    if filters.get("root_lot"):
        conditions.append("b.root_lot = %(root_lot)s")
        params["root_lot"] = filters.root_lot
    if filters.get("process_stage"):
        conditions.append("b.process_stage = %(process_stage)s")
        params["process_stage"] = filters.process_stage
    if filters.get("from_date"):
        conditions.append("sle.posting_date >= %(from_date)s")
        params["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("sle.posting_date <= %(to_date)s")
        params["to_date"] = filters.to_date

    rows = frappe.db.sql("""
        SELECT b.root_lot, b.process_stage, sle.batch_no, sle.item_code,
               sle.posting_date, sle.posting_time, sle.voucher_type,
               sle.voucher_no, sle.warehouse, sle.actual_qty AS qty,
               sle.stock_uom AS uom,
               COALESCE(lps.sequence, 99) AS stage_seq
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        LEFT JOIN `tabLot Process Stage` lps ON lps.name = b.process_stage
        WHERE {conditions}
        ORDER BY b.root_lot, stage_seq,
                 sle.posting_date, sle.posting_time, sle.name
    """.format(conditions=" AND ".join(conditions)), params, as_dict=True)

    # Resolve party (supplier/customer) per voucher, grouped by voucher_type
    # to keep it to one query per voucher type (Phase 3A4).
    by_type = {}
    for r in rows:
        by_type.setdefault(r.voucher_type, []).append(r.voucher_no)
    party_lookup = {vt: _party_map(vt, nos) for vt, nos in by_type.items()}

    balances = {}
    for r in rows:
        key = r.batch_no
        balances[key] = balances.get(key, 0) + flt(r.qty)
        r.running_balance = round(balances[key], 3)
        r.qty = flt(r.qty)
        r.party = party_lookup.get(r.voucher_type, {}).get(r.voucher_no)
        r.pop("stage_seq", None)
    return rows
