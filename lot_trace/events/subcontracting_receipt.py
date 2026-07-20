# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Subcontracting Receipt handler (canonical).
# All hook names present (before_submit, on_submit, on_cancel, before_cancel)
# so any hooks.py variant works without AttributeError.

import frappe

from lot_trace.events import resolver_v2
from lot_trace.events import lot_factory_v2


def before_submit(doc, method=None):
    """Auto-resolve lot from consumed greige batch, create DY/CT batches."""
    for row in doc.items:
        if not _is_processed_item(row.item_code):
            continue
        stage = "CT" if _is_cut_item(row.item_code) else "DY"
        root_lot, yarn_row = _resolve_lot_for_row(doc, row)
        if not root_lot:
            frappe.throw(
                f"Row {row.idx}: could not auto-resolve the lot for "
                f"{row.item_code}. Ensure the consumed greige batch is listed "
                f"in Supplied Items, or set Root Lot on the row."
            )
        lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
        abbr = (yarn_row or {}).get("item_abbr")
        color = resolver_v2.color_abbr_for_item(row.item_code) if stage == "DY" else None
        batch_name = resolver_v2.render_batch_name(
            lot_code, stage, abbr=abbr, color_abbr=color
        )
        lot_factory_v2.ensure_batch(batch_name, row.item_code, root_lot, stage=stage)
        row.batch_no = batch_name
        frappe.db.set_value("Root Lot", root_lot, "current_stage", stage)


def on_submit(doc, method=None):
    """Compatibility stub — work happens in before_submit."""
    pass


def before_cancel(doc, method=None):
    """Skip circular link check against our tracking doctypes."""
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = ["Root Lot", "Batch", "Lot Receipt"]


def on_cancel(doc, method=None):
    """Roll the lot's stage back to DY/NT based on remaining batches."""
    for row in doc.items:
        if not row.get("batch_no"):
            continue
        rl = frappe.db.get_value("Batch", row.batch_no, "custom_root_lot")
        if rl and frappe.db.exists("Root Lot", rl):
            frappe.db.set_value("Root Lot", rl, "current_stage", "NT")


# ---------------------------------------------------------------------------
# Lot resolution
# ---------------------------------------------------------------------------

def _resolve_lot_for_row(doc, row):
    root_lot = _root_lot_from_consumed(doc, row)
    if root_lot:
        return root_lot, _yarn_row_for(root_lot, row.item_code)

    override = row.get("custom_root_lot")
    if override:
        return override, _yarn_row_for(override, row.item_code)

    return None, None


def _root_lot_from_consumed(doc, row):
    base_out = resolver_v2.extract_base_yarn_item(row.item_code)
    supplied = getattr(doc, "supplied_items", None) or []
    consumed = [
        (s.get("rm_item_code") or s.get("item_code"), s.get("batch_no"))
        for s in supplied if s.get("batch_no")
    ]

    for item_code, batch_no in consumed:
        if resolver_v2.extract_base_yarn_item(item_code) == base_out:
            rl = frappe.db.get_value("Batch", batch_no, "custom_root_lot")
            if rl:
                return rl

    lots = set()
    for _item, batch_no in consumed:
        rl = frappe.db.get_value("Batch", batch_no, "custom_root_lot")
        if rl:
            lots.add(rl)
    if len(lots) == 1:
        return next(iter(lots))
    return None


def _yarn_row_for(root_lot, output_item_code):
    rule = frappe.db.get_value("Root Lot", root_lot, "naming_rule")
    if not rule:
        return None
    base = resolver_v2.extract_base_yarn_item(output_item_code)
    yarns = frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"parent": rule, "yarn_item": base},
        fields=["yarn_item", "role", "item_abbr"],
    )
    if yarns:
        return yarns[0]
    yarns = frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"parent": rule, "role": "Primary"},
        fields=["yarn_item", "role", "item_abbr"],
    )
    return yarns[0] if yarns else None


def _is_processed_item(item_code):
    return _is_dyed_item(item_code) or _is_cut_item(item_code)


def _is_dyed_item(item_code):
    up = (item_code or "").upper()
    return "-DYE" in up or "-DY" in up


def _is_cut_item(item_code):
    up = (item_code or "").upper()
    return "-CT" in up or "CUT" in up
