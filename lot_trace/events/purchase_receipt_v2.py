# -*- coding: utf-8 -*-
# Phase 6 V2 — Purchase Receipt handler (simplified)

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2
from lot_trace.events import lot_factory_v2


def before_submit(doc, method=None):
    """Set batch_no for greige/weaving items. Create/reuse Root Lot."""
    greige_rows = []
    weave_rows = []

    for row in doc.items:
        rule, yarn_row = resolver_v2.find_naming_rule_for_item(row.item_code)
        if rule:
            greige_rows.append((row, rule, yarn_row))
            continue

    if greige_rows:
        _handle_greige_intake(doc, greige_rows)


def on_cancel(doc, method=None):
    """Roll back Lot Receipts when PR is cancelled."""
    for row in doc.items:
        rl = frappe.db.get_value("Batch", row.get("batch_no"), "custom_root_lot") \
            if row.get("batch_no") else None
        if not rl:
            continue
        lot = frappe.get_doc("Root Lot", rl)
        kept = [r for r in lot.get("lot_receipts", []) if r.source_doc != doc.name]
        if len(kept) != len(lot.get("lot_receipts", [])):
            lot.set("lot_receipts", kept)
            lot.intake_complete = 0
            lot.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Greige intake
# ---------------------------------------------------------------------------

def _handle_greige_intake(doc, greige_rows):
    """Create/reuse ONE lot per (rule, production run)."""
    po_root_lot = _po_root_lot(doc)

    # Group by rule
    by_rule = {}
    for row, rule, yarn_row in greige_rows:
        by_rule.setdefault(rule, []).append((row, yarn_row))

    for rule, rows in by_rule.items():
        # Is primary yarn in this receipt?
        primary_present = any(yr["role"] == "Primary" for _, yr in rows)

        if primary_present:
            root_lot = lot_factory_v2.create_root_lot(rule)
        else:
            root_lot = _resolve_secondary_only_lot(rule, rows, po_root_lot, doc)

        for row, yarn_row in rows:
            _attach_nt_batch(doc, row, rule, root_lot, yarn_row)


def _resolve_secondary_only_lot(rule, rows, po_root_lot, doc):
    """PR has only secondary yarn(s). Attach to open lot."""
    first_item = rows[0][0].item_code
    decision = resolver_v2.resolve_open_lot(first_item, po_root_lot=po_root_lot)

    if decision["action"] == "reuse":
        if decision["ambiguous"]:
            frappe.throw(
                f"Multiple open lots are waiting for {first_item}. "
                f"Link the Purchase Order to a specific lot, or receive against "
                f"a lot manually."
            )
        return decision["root_lot"]

    frappe.throw(
        f"{first_item} is a secondary yarn, but no open lot is waiting for it. "
        f"Receive the primary yarn first."
    )


def _attach_nt_batch(doc, row, rule, root_lot, yarn_row):
    """Create NT batch and record receipt."""
    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
    abbr = yarn_row.get("item_abbr")
    batch_name = resolver_v2.render_batch_name(lot_code, "NT", abbr=abbr)
    lot_factory_v2.ensure_batch(batch_name, row.item_code, root_lot, stage="NT")
    row.batch_no = batch_name
    lot_factory_v2.record_lot_receipt(
        root_lot=root_lot,
        yarn_item=row.item_code,
        item_abbr=abbr or "",
        nt_batch=batch_name,
        received_kg=flt(row.qty),
        source_doctype=doc.doctype,
        source_doc=doc.name,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _po_root_lot(doc):
    """Extract Root Lot from linked Purchase Order if available."""
    for row in doc.items:
        po = row.get("purchase_order")
        if po:
            rl = frappe.db.get_value("Purchase Order", po, "custom_root_lot")
            if rl:
                return rl
    return None
