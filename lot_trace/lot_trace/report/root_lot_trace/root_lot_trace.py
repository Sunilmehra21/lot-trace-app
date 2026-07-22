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
        {"fieldname": "warehouse", "label": _("Warehouse"),
         "fieldtype": "Link", "options": "Warehouse", "width": 150},
        {"fieldname": "qty", "label": _("Qty"),
         "fieldtype": "Float", "width": 100},
        {"fieldname": "uom", "label": _("UOM"),
         "fieldtype": "Data", "width": 70},
        {"fieldname": "running_balance", "label": _("Batch Balance"),
         "fieldtype": "Float", "width": 110},
    ]


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
               sle.stock_uom AS uom
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE {conditions}
        ORDER BY b.root_lot, b.process_stage,
                 sle.posting_date, sle.posting_time, sle.name
    """.format(conditions=" AND ".join(conditions)), params, as_dict=True)

    balances = {}
    for r in rows:
        key = r.batch_no
        balances[key] = balances.get(key, 0) + flt(r.qty)
        r.running_balance = round(balances[key], 3)
        r.qty = flt(r.qty)
    return rows
