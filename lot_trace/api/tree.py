# -*- coding: utf-8 -*-
# Lot Trace Tree API: hierarchical view of a lot's batches and movements.

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_lot_tree(root_lot):
    """Tree: Root Lot -> stage batches -> stock movements."""
    frappe.has_permission("Root Lot", "read", throw=True)
    if not root_lot:
        return {}

    lot = frappe.db.get_value(
        "Root Lot", root_lot,
        ["name", "lot_code", "product", "status", "current_stage",
         "received_qty", "uom", "fg_qty", "dispatched_qty", "weaved_pcs",
         "yarn_in_process_qty", "sales_order"],
        as_dict=True)
    if not lot:
        return {}

    batches = frappe.get_all(
        "Batch",
        filters={"root_lot": root_lot},
        fields=["name", "item", "process_stage"])

    stage_seq = {s.name: s.sequence for s in frappe.get_all(
        "Lot Process Stage", fields=["name", "sequence"])}
    batches.sort(key=lambda b: stage_seq.get(b.process_stage, 99))

    nodes = []
    for b in batches:
        movements = frappe.db.sql("""
            SELECT voucher_type, voucher_no, actual_qty, stock_uom,
                   posting_date, warehouse
            FROM `tabStock Ledger Entry`
            WHERE batch_no = %s AND is_cancelled = 0
            ORDER BY posting_date, posting_time, name
        """, b.name, as_dict=True)
        balance = sum(flt(m.actual_qty) for m in movements)
        nodes.append({
            "batch": b.name,
            "item": b.item,
            "stage": b.process_stage,
            "balance": round(balance, 2),
            "movements": [{
                "voucher_type": m.voucher_type,
                "voucher_no": m.voucher_no,
                "qty": flt(m.actual_qty),
                "uom": m.stock_uom,
                "date": str(m.posting_date),
                "warehouse": m.warehouse,
            } for m in movements],
        })

    return {"lot": lot, "batches": nodes}


@frappe.whitelist()
def get_trace_tree(root_lot):
    """Alias kept for older page JS."""
    return get_lot_tree(root_lot)
