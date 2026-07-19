# -*- coding: utf-8 -*-
# Phase 6 — Subcontracting Receipt handler (dyeing / cutting).
#
# KEY IMPROVEMENT: the root lot is derived AUTOMATICALLY from the consumed
# supplied greige batch. Subcontracting in ERPNext consumes supplied items that
# carry batch numbers; that greige batch already encodes its root lot (via
# Batch.custom_root_lot). So no manual lot selection is needed for a multi-item,
# multi-colour single SR.
#
# Fallbacks (in order): consumed batch -> PO/SR custom_root_lot -> infer from
# base item + supplier. Ask the user only if still ambiguous.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver
from lot_trace.events.lot_factory import ensure_batch


def before_submit(doc, method=None):
    for row in doc.items:
        if not _is_processed_item(row.item_code):
            continue
        stage = "CT" if _is_cut_item(row.item_code) else "DY"
        root_lot, trace = _resolve_lot_for_row(doc, row)
        if not root_lot:
            frappe.throw(
                f"Row {row.idx}: could not resolve the source lot for dyed item "
                f"{row.item_code}. Ensure the greige yarn consumed carries its "
                f"batch, or set Root Lot manually."
            )
        profile = frappe.db.get_value("Root Lot", root_lot, "profile")
        lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
        color = resolver.color_abbr_for_item(row.item_code) if stage == "DY" else None
        batch_name = resolver.render_batch_name(
            profile, lot_code, stage, trace_row=trace, color_abbr=color
        )
        ensure_batch(batch_name, row.item_code, root_lot, stage=stage)
        row.batch_no = batch_name
        frappe.db.set_value("Root Lot", root_lot, "current_stage", stage)


# ---------------------------------------------------------------------------
# Lot resolution
# ---------------------------------------------------------------------------

def _resolve_lot_for_row(doc, row):
    """Return (root_lot, trace_row) for a dyed/cut output row.

    Priority:
      1. Root lot of the consumed supplied greige batch (most reliable).
      2. Explicit custom_root_lot on the row (manual override).
      3. Infer from base item + supplier (exactly one open match).
    """
    # 1) Consumed supplied batch
    root_lot = _root_lot_from_consumed(doc, row)
    if root_lot:
        return root_lot, _trace_for(root_lot, row.item_code)

    # 2) Manual override on the row
    override = row.get("custom_root_lot")
    if override:
        return override, _trace_for(override, row.item_code)

    # 3) Infer
    base = resolver.extract_base_yarn_item(row.item_code)
    candidates = _infer_lots(base, doc.supplier)
    if len(candidates) == 1:
        return candidates[0], _trace_for(candidates[0], row.item_code)
    if len(candidates) > 1:
        frappe.throw(
            f"Row {row.idx}: {row.item_code} could match multiple lots "
            f"({', '.join(candidates)}). Set Root Lot on the row."
        )
    return None, None


def _root_lot_from_consumed(doc, row):
    """Find the greige batch consumed for this output row and read its lot.

    ERPNext subcontracting stores supplied/consumed items. We look for a
    consumed batch whose base item matches this output's base item.
    """
    base_out = resolver.extract_base_yarn_item(row.item_code)

    # Supplied Items table on the SR (consumed raw materials).
    supplied = getattr(doc, "supplied_items", None) or []
    consumed_batches = []
    for s in supplied:
        b = s.get("batch_no")
        if b:
            consumed_batches.append((s.get("rm_item_code") or s.get("item_code"), b))

    # Prefer a consumed batch whose base item equals this output's base item.
    for item_code, batch_no in consumed_batches:
        if resolver.extract_base_yarn_item(item_code) == base_out:
            rl = frappe.db.get_value("Batch", batch_no, "custom_root_lot")
            if rl:
                return rl

    # Otherwise, if all consumed batches point to ONE lot, use it.
    lots = set()
    for _item_code, batch_no in consumed_batches:
        rl = frappe.db.get_value("Batch", batch_no, "custom_root_lot")
        if rl:
            lots.add(rl)
    if len(lots) == 1:
        return next(iter(lots))
    return None


def _trace_for(root_lot, output_item_code):
    """Return the Trace Item row (dict) matching this output's base yarn."""
    profile = frappe.db.get_value("Root Lot", root_lot, "profile")
    base = resolver.extract_base_yarn_item(output_item_code)
    rows = frappe.get_all(
        "Lot Trace Item",
        filters={"parent": profile, "yarn_item": base},
        fields=["name", "item_abbr", "yarn_item", "role", "bom_kg_per_pc"],
    )
    if rows:
        return rows[0]
    # Fallback: primary row (keeps a valid abbr in the batch name).
    return resolver.get_primary_row(profile)


def _infer_lots(base_item, supplier):
    """Open lots that received this base yarn and are not yet fully consumed."""
    lots = frappe.get_all(
        "Root Lot",
        filters={"status": ["!=", "Completed"]},
        fields=["name", "profile"],
        order_by="creation asc",
    )
    out = []
    for lot in lots:
        got = frappe.db.exists(
            "Lot Receipt", {"parent": lot.name, "yarn_item": base_item}
        )
        if got:
            out.append(lot.name)
    return out


# ---------------------------------------------------------------------------
# Item type helpers
# ---------------------------------------------------------------------------

def _is_processed_item(item_code):
    return _is_dyed_item(item_code) or _is_cut_item(item_code)


def _is_dyed_item(item_code):
    if not item_code:
        return False
    up = item_code.upper()
    return "-DYE" in up or "-DY" in up


def _is_cut_item(item_code):
    if not item_code:
        return False
    up = item_code.upper()
    return "-CT" in up or "CUT" in up
