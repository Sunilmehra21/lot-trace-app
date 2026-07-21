# -*- coding: utf-8 -*-
# V7 — Data for the Lot Flow Chart and Order Lot Overview pages.
# All numbers derive from Lot Receipts (child table) + live batch stock,
# never from the removed legacy fields — this fixes the empty reports.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2, lot_factory_v2


def _lot_filters(sales_order=None, product=None, root_lot=None, status=None):
    f = {}
    if sales_order:
        f["sales_order"] = sales_order
    if product:
        f["product"] = product
    if root_lot:
        f["name"] = root_lot
    if status:
        f["status"] = status
    return f


@frappe.whitelist()
def get_flow_chart(sales_order=None, product=None, root_lot=None, **kwargs):
    stages = resolver_v2.get_flow_stages()
    lots = frappe.get_all(
        "Root Lot",
        filters=_lot_filters(sales_order, product, root_lot),
        fields=["name", "lot_code", "product", "status", "current_stage",
                "sales_order", "total_yarn_received_kg"],
        order_by="creation desc", limit_page_length=50)

    summary = {"yarn_received_kg": 0, "in_process_kg": 0, "weaved_pcs": 0,
               "finished_qty": 0, "dispatched_qty": 0,
               "open_exceptions": 0, "lot_count": len(lots)}

    for lot in lots:
        lot_factory_v2.recompute_totals(lot.name)  # always-fresh numbers
        vals = frappe.db.get_value(
            "Root Lot", lot.name,
            ["total_yarn_received_kg", "yarn_in_process_kg",
             "weaved_pcs_received", "finished_goods_qty", "dispatched_qty"],
            as_dict=True)
        lot.update(vals)

        # per-stage balances for the grid cells
        lot["stage_qty"] = {}
        for code, _label in stages:
            lot["stage_qty"][code] = lot_factory_v2.stage_balance(
                lot.name, [code])

        summary["yarn_received_kg"] += flt(vals.total_yarn_received_kg)
        summary["in_process_kg"] += flt(vals.yarn_in_process_kg)
        summary["weaved_pcs"] += flt(vals.weaved_pcs_received)
        summary["finished_qty"] += flt(vals.finished_goods_qty)
        summary["dispatched_qty"] += flt(vals.dispatched_qty)

    if frappe.db.exists("DocType", "Lot Exception"):
        ex_filters = {"docstatus": ["<", 2]}
        if root_lot:
            ex_filters["root_lot"] = root_lot
        try:
            summary["open_exceptions"] = frappe.db.count(
                "Lot Exception", ex_filters)
        except Exception:
            summary["open_exceptions"] = 0

    return {
        "stages": [{"code": c, "label": l} for c, l in stages],
        "lots": lots,
        "summary": summary,
    }


@frappe.whitelist()
def get_order_overview(sales_order=None, product=None, status=None, **kwargs):
    lots = frappe.get_all(
        "Root Lot",
        filters=_lot_filters(sales_order, product, None, status),
        fields=["name", "lot_code", "product", "sales_order", "end_customer",
                "status", "current_stage", "intake_complete"],
        order_by="creation desc", limit_page_length=200)

    for lot in lots:
        lot_factory_v2.recompute_totals(lot.name)
        lot.update(frappe.db.get_value(
            "Root Lot", lot.name,
            ["total_yarn_received_kg", "yarn_in_process_kg",
             "weaved_pcs_received", "finished_goods_qty", "dispatched_qty"],
            as_dict=True))
        lot["batch_count"] = frappe.db.count(
            "Batch", {"custom_root_lot": lot.name})

    return {"lots": lots}
