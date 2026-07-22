# -*- coding: utf-8 -*-
# At Weaver Balance report: dyed yarn sent to weavers (DN/SI) minus
# yarn consumed in Subcontracting Receipts — per lot / batch / weaver.
# Reuses the single API engine (P2/P3): lot_trace.api.lot.get_at_weaver_balance.

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
        {"fieldname": "batch", "label": _("Dyed Batch"),
         "fieldtype": "Link", "options": "Batch", "width": 200},
        {"fieldname": "item", "label": _("Dyed Yarn Item"),
         "fieldtype": "Link", "options": "Item", "width": 170},
        {"fieldname": "weaver", "label": _("Weaver (Customer)"),
         "fieldtype": "Link", "options": "Customer", "width": 160},
        {"fieldname": "sent_to_weaver", "label": _("Sent (kg)"),
         "fieldtype": "Float", "width": 110},
        {"fieldname": "consumed_at_weaver", "label": _("Consumed (kg)"),
         "fieldtype": "Float", "width": 120},
        {"fieldname": "balance", "label": _("At Weaver (kg)"),
         "fieldtype": "Float", "width": 120},
    ]


def get_data(filters):
    from lot_trace.api.lot import get_at_weaver_balance

    rows = get_at_weaver_balance(
        root_lot=filters.get("root_lot"),
        weaver=filters.get("weaver"))

    out = []
    for r in rows:
        weaver = _main_weaver_for_batch(r["batch"], filters.get("weaver"))
        out.append({
            "root_lot": r["root_lot"],
            "batch": r["batch"],
            "item": r["item"],
            "weaver": weaver,
            "sent_to_weaver": flt(r["sent_to_weaver"]),
            "consumed_at_weaver": flt(r["consumed_at_weaver"]),
            "balance": flt(r["balance"]),
        })
    return out


def _main_weaver_for_batch(batch_no, weaver=None):
    """Customer that received the most of this batch via Delivery Note."""
    if weaver:
        return weaver
    row = frappe.db.sql("""
        SELECT dn.customer, SUM(-sle.actual_qty) AS qty
        FROM `tabStock Ledger Entry` sle
        JOIN `tabDelivery Note` dn ON sle.voucher_type = 'Delivery Note'
             AND sle.voucher_no = dn.name
        WHERE sle.batch_no = %s AND sle.is_cancelled = 0
          AND sle.actual_qty < 0 AND dn.docstatus = 1
        GROUP BY dn.customer
        ORDER BY qty DESC
        LIMIT 1
    """, batch_no)
    return row[0][0] if row else None
