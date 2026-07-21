# -*- coding: utf-8 -*-
# V7 — Lot Trace Tree data. get_lot_tree is kept as an alias so any old
# JS keeps working.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2


@frappe.whitelist()
def get_trace_tree(root_lot=None, product=None, sales_order=None, **kwargs):
    filters = {}
    if root_lot:
        filters["name"] = root_lot
    if product:
        filters["product"] = product
    if sales_order:
        filters["sales_order"] = sales_order
    if not filters:
        return {"lots": []}

    lots = frappe.get_all(
        "Root Lot", filters=filters,
        fields=["name", "lot_code", "product", "naming_rule", "sales_order",
                "status", "current_stage", "intake_complete",
                "total_yarn_received_kg"],
        order_by="creation desc", limit_page_length=20)

    out = []
    for lot in lots:
        node = dict(lot)
        node["receipts"] = frappe.get_all(
            "Lot Receipt", filters={"parent": lot.name},
            fields=["yarn_item", "item_abbr", "nt_batch", "received_kg",
                    "source_doctype", "source_doc"],
            order_by="idx asc")
        node["stages"] = _stage_nodes(lot.name)
        out.append(node)
    return {"lots": out}


def _stage_nodes(root_lot):
    batches = frappe.get_all(
        "Batch", filters={"custom_root_lot": root_lot},
        fields=["name", "item", "custom_stage"])
    by_stage = {}
    for b in batches:
        by_stage.setdefault(b.custom_stage or "NT", []).append(b)

    nodes = []
    for code, label in resolver_v2.get_flow_stages():
        if code not in by_stage:
            continue
        stage_batches = []
        for b in by_stage[code]:
            qty = frappe.db.sql(
                "select sum(actual_qty) from `tabStock Ledger Entry` "
                "where batch_no=%s and is_cancelled=0", (b.name,))
            docs = frappe.get_all(
                "Stock Ledger Entry",
                filters={"batch_no": b.name, "is_cancelled": 0},
                fields=["distinct voucher_type as voucher_type",
                        "voucher_no"],
                limit_page_length=20)
            stage_batches.append({
                "batch": b.name, "item": b.item,
                "qty": flt(qty[0][0]) if qty else 0,
                "documents": docs,
            })
        nodes.append({"stage": code, "label": label,
                      "batches": stage_batches})
    return nodes


# Backwards-compatible alias
@frappe.whitelist()
def get_lot_tree(root_lot=None, product=None, sales_order=None, **kwargs):
    return get_trace_tree(root_lot=root_lot, product=product,
                          sales_order=sales_order, **kwargs)
