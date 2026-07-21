# -*- coding: utf-8 -*-
# V7 — Subcontracting Receipt hooks.
# The root lot is AUTO-RESOLVED from the consumed supplied batch
# (Batch.custom_root_lot) — the user never picks a lot manually.
# Consumed stage NT -> produced batch is DY (dyeing job).
# Consumed stage DY -> produced batch is WV (weaving job).

import frappe

from lot_trace.events import resolver_v2, lot_factory_v2

_NEXT = {"NT": "DY", "DY": "WV", "WV": "CT"}


def before_submit(doc, method=None):
    consumed = _consumed_lot_and_stage(doc)
    if not consumed:
        return
    root_lot, consumed_stage, consumed_item = consumed
    produced_stage = _NEXT.get(consumed_stage, "DY")
    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot

    touched = False
    for item in doc.items:
        if item.get("batch_no"):
            continue
        if produced_stage == "DY":
            _, yarn_row = resolver_v2.find_naming_rule_for_item(consumed_item)
            abbr = yarn_row.item_abbr if yarn_row else "A"
            color = resolver_v2.color_abbr_for_item(item.item_code)
            batch = resolver_v2.render_batch_name(
                lot_code, "DY", abbr=abbr, color=color)
        else:
            batch = resolver_v2.render_batch_name(lot_code, produced_stage)
        lot_factory_v2.ensure_batch(
            batch, item.item_code, root_lot, produced_stage)
        item.batch_no = batch
        if hasattr(item, "custom_root_lot"):
            item.custom_root_lot = root_lot
        touched = True

    if touched:
        doc.flags.lot_trace_lot = root_lot
        doc.flags.lot_trace_stage = produced_stage


def _consumed_lot_and_stage(doc):
    """First consumed supplied batch that belongs to a Root Lot decides."""
    for row in (doc.get("supplied_items") or []):
        batch = row.get("batch_no")
        if not batch:
            continue
        info = frappe.db.get_value(
            "Batch", batch, ["custom_root_lot", "custom_stage", "item"],
            as_dict=True)
        if info and info.custom_root_lot:
            return (info.custom_root_lot,
                    info.custom_stage or "NT", info.item)
    return None


def on_submit(doc, method=None):
    root_lot = doc.flags.get("lot_trace_lot")
    if root_lot:
        lot_factory_v2.set_current_stage(
            root_lot, doc.flags.get("lot_trace_stage") or "DY")
        lot_factory_v2.recompute_totals(root_lot)


def before_cancel(doc, method=None):
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = ["Root Lot", "Batch", "Lot Receipt"]


def on_cancel(doc, method=None):
    lots = {frappe.db.get_value("Batch", i.batch_no, "custom_root_lot")
            for i in doc.items if i.get("batch_no")}
    for lot in filter(None, lots):
        lot_factory_v2.recompute_totals(lot)
