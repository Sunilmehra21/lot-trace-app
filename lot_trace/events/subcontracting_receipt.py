# -*- coding: utf-8 -*-
# Subcontracting Receipt hooks.
# Root Lot is AUTO-RESOLVED from the consumed supplied batch (Batch.root_lot).
# Stage progression: NT consumed -> DY produced; DY -> WV; WV -> CT.
# Never touches core stock/valuation logic (design P5).

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events import common, lot_factory


def before_submit(doc, method=None):
    consumed = _consumed_lot_and_stage(doc)
    if not consumed:
        return
    root_lot, consumed_stage, consumed_item = consumed

    produced_stage = common.next_stage_after(consumed_stage, root_lot)
    if not produced_stage:
        return

    lot_code = frappe.db.get_value(
        "Root Lot", root_lot, "lot_code") or root_lot

    touched = False
    for item in doc.items:
        if item.get("batch_no"):
            continue
        batch_no = common.create_stage_batch(
            lot_code, produced_stage, item.item_code)
        item.batch_no = batch_no
        item.root_lot = root_lot
        touched = True

    if touched:
        doc.flags.lot_trace_lot = root_lot
        doc.flags.lot_trace_stage = produced_stage
        doc.flags.lot_trace_consumed_stage = consumed_stage


def _consumed_lot_and_stage(doc):
    """First consumed supplied batch that belongs to a Root Lot decides."""
    for row in (doc.get("supplied_items") or []):
        batch = row.get("batch_no")
        if not batch:
            continue
        info = frappe.db.get_value(
            "Batch", batch,
            ["root_lot", "process_stage", "item"], as_dict=True)
        if info and info.root_lot:
            return info.root_lot, info.process_stage or "NT", info.item
    return None


def on_submit(doc, method=None):
    root_lot = doc.flags.get("lot_trace_lot")
    if not root_lot:
        return
    lot_factory.recompute_totals(root_lot)
    common.check_stage_loss(
        root_lot=root_lot,
        stage_code=doc.flags.get("lot_trace_consumed_stage", "NT"),
        input_qty=sum(
            flt(r.consumed_qty) for r in (doc.get("supplied_items") or [])),
        output_qty=sum(
            flt(i.qty) for i in doc.items),
        erp_doc_type="Subcontracting Receipt",
        erp_doc_name=doc.name,
    )


def before_cancel(doc, method=None):
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = ["Root Lot", "Batch", "Lot Receipt"]


def on_cancel(doc, method=None):
    batches = [i.batch_no for i in doc.items if i.get("batch_no")]
    lot_factory.recompute_for_batches(batches)