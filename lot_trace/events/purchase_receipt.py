# -*- coding: utf-8 -*-
# Phase 6 — Purchase Receipt handler (greige yarn intake + weaving FG).
#
# On submit of a Purchase Receipt:
#   * Greige yarn rows  -> create/reuse ONE Root Lot for the production run,
#                          create per-item NT batches, record Lot Receipts.
#   * Weaving FG rows   -> resolve the lot from the dyed yarn at the weaver,
#                          create the WV batch, validate BOM consumption.
#
# We only set row.batch_no and create Root Lot / Batch docs. Stock, SLE and
# valuation are left entirely to standard ERPNext (user requirement #4).

import frappe
from frappe.utils import flt

from lot_trace.events import resolver
from lot_trace.events.lot_factory import (
    create_root_lot,
    ensure_batch,
    record_lot_receipt,
)


def on_cancel(doc, method=None):
    """Roll back Lot Receipts recorded by this PR. Batches/lots are kept
    (they may hold stock from other vouchers); we only remove our receipt rows
    and re-open intake if needed."""
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


def before_submit(doc, method=None):
    """Assign batch numbers and stage lot decisions before stock posts."""
    greige_rows = []
    weave_rows = []

    for row in doc.items:
        profile, trace = resolver.resolve_profile_for_item(row.item_code)
        if profile:
            greige_rows.append((row, profile, trace))
            continue
        # Is this a finished good with a profile (weaving output)?
        if _is_weaving_output(row.item_code):
            weave_rows.append(row)

    if greige_rows:
        _handle_greige_intake(doc, greige_rows)
    for row in weave_rows:
        _handle_weaving_row(doc, row)


# ---------------------------------------------------------------------------
# Greige intake
# ---------------------------------------------------------------------------

def _handle_greige_intake(doc, greige_rows):
    """Create/reuse ONE lot per (profile, production run) and NT batches.

    Multiple rows of the SAME profile in one PR share one lot. The primary
    yarn (if present) opens/creates the lot; secondaries attach.
    """
    po_root_lot = _po_root_lot(doc)

    # Group rows by profile so a single multi-item PR maps cleanly.
    by_profile = {}
    for row, profile, trace in greige_rows:
        by_profile.setdefault(profile, []).append((row, trace))

    for profile, rows in by_profile.items():
        # Does this PR contain the primary yarn? Then this is a NEW run.
        primary_present = any(t.role == "Primary" for _r, t in rows)

        if primary_present:
            root_lot = create_root_lot(profile, po_root_lot=po_root_lot)
        else:
            root_lot = _resolve_secondary_only_lot(profile, rows, po_root_lot, doc)

        for row, trace in rows:
            _attach_nt_batch(doc, row, profile, root_lot, trace)


def _resolve_secondary_only_lot(profile, rows, po_root_lot, doc):
    """PR has only secondary yarn(s) of this profile. Attach to an open lot."""
    # Use the first row to probe; all secondaries here go to the same run
    # (same PR = same delivery). Resolve once, reuse for all.
    first_item = rows[0][0].item_code
    decision = resolver.resolve_open_lot(first_item, po_root_lot=po_root_lot)

    if decision["action"] == "reuse":
        if decision["ambiguous"]:
            frappe.throw(
                f"Multiple open lots of {profile} were opened the same day and "
                f"are waiting for {first_item}. Set the Root Lot on the linked "
                f"Purchase Order, or receive against a specific lot. "
                f"Candidates: {', '.join(decision['candidates'])}"
            )
        return decision["root_lot"]

    # action == 'hold' -> secondary arrived before its primary.
    frappe.throw(
        f"{first_item} is a secondary yarn for {profile}, but no open production "
        f"lot is waiting for it. Receive the primary yarn first, or link this "
        f"receipt to an existing Purchase Order that carries the Root Lot."
    )


def _attach_nt_batch(doc, row, profile, root_lot, trace):
    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
    batch_name = resolver.render_batch_name(profile, lot_code, "NT", trace)
    ensure_batch(batch_name, row.item_code, root_lot, stage="NT")
    row.batch_no = batch_name
    record_lot_receipt(
        root_lot=root_lot,
        yarn_item=row.item_code,
        item_abbr=trace.item_abbr,
        nt_batch=batch_name,
        received_kg=flt(row.qty),
        source_doctype=doc.doctype,
        source_doc=doc.name,
    )


# ---------------------------------------------------------------------------
# Weaving output
# ---------------------------------------------------------------------------

def _is_weaving_output(item_code):
    """True if item is a finished product that has a Lot Trace Profile."""
    return bool(
        frappe.db.exists("Lot Trace Profile", {"product": item_code, "active": 1})
    )


def _handle_weaving_row(doc, row):
    """Resolve the lot whose dyed yarn is at this weaver, create WV batch."""
    profile = frappe.db.get_value(
        "Lot Trace Profile", {"product": row.item_code, "active": 1}, "name"
    )
    root_lot = _lot_at_supplier(profile, doc.supplier)
    if not root_lot:
        frappe.throw(
            f"Could not resolve which production lot's dyed yarn is with "
            f"weaver {doc.supplier} for {row.item_code}. Set the Root Lot "
            f"manually on this row."
        )
    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
    batch_name = resolver.render_batch_name(profile, lot_code, "WV")
    ensure_batch(batch_name, row.item_code, root_lot, stage="WV")
    row.batch_no = batch_name

    _validate_weaving_consumption(profile, root_lot, doc.supplier, flt(row.qty))
    frappe.db.set_value("Root Lot", root_lot, "current_stage", "WV")


def _lot_at_supplier(profile, supplier):
    """Find the open lot of this profile whose dyed batches are stocked at the
    supplier's (weaver's) warehouse. FIFO if more than one."""
    open_lots = frappe.get_all(
        "Root Lot",
        filters={"profile": profile, "intake_complete": 1, "current_stage": ["in", ["DY", "NT"]]},
        fields=["name"],
        order_by="creation asc",
    )
    supplier_wh = _supplier_warehouse(supplier)
    for lot in open_lots:
        dy_batches = frappe.get_all(
            "Batch", filters={"custom_root_lot": lot.name, "custom_stage": "DY"},
            fields=["name"],
        )
        for b in dy_batches:
            bal = _batch_balance_in_wh(b.name, supplier_wh)
            if bal > 0.001:
                return lot.name
    # Fallback: single open lot at DY stage
    if len(open_lots) == 1:
        return open_lots[0].name
    return None


def _validate_weaving_consumption(profile, root_lot, supplier, pcs):
    """Informational BOM check per yarn item; warn (not block) beyond tolerance.

    We never alter stock — standard ERP subcontracting consumes the yarn.
    This only flags a discrepancy for the user to review.
    """
    tol = flt(frappe.db.get_value("Lot Trace Profile", profile, "weaving_tolerance_pct")) or 2.0
    trace_items = frappe.get_all(
        "Lot Trace Item", filters={"parent": profile},
        fields=["yarn_item", "item_abbr", "bom_kg_per_pc"],
    )
    supplier_wh = _supplier_warehouse(supplier)
    messages = []
    for ti in trace_items:
        expected = flt(ti.bom_kg_per_pc) * flt(pcs)
        if expected <= 0:
            continue
        available = _yarn_available_for_lot(root_lot, ti.yarn_item, supplier_wh)
        if available + (expected * tol / 100.0) + 0.5 < expected:
            messages.append(
                f"  {ti.yarn_item}: needs ~{expected:.1f} kg, only {available:.1f} kg "
                f"of this lot at weaver"
            )
    if messages:
        frappe.msgprint(
            "Weaving consumption check (informational):\n" + "\n".join(messages),
            title="Yarn shortfall vs BOM", indicator="orange",
        )


# ---------------------------------------------------------------------------
# Small stock READ helpers (never write)
# ---------------------------------------------------------------------------

def _po_root_lot(doc):
    """If PR rows link to a PO carrying a Root Lot, return it."""
    for row in doc.items:
        po = row.get("purchase_order")
        if po:
            rl = frappe.db.get_value("Purchase Order", po, "custom_root_lot")
            if rl:
                return rl
    return None


def _supplier_warehouse(supplier):
    return frappe.db.get_value(
        "Warehouse", {"custom_supplier": supplier, "is_group": 0}, "name"
    ) or frappe.db.get_value(
        "Warehouse", {"warehouse_name": ["like", f"%{supplier}%"]}, "name"
    )


def _batch_balance_in_wh(batch_no, warehouse):
    if not warehouse:
        return 0.0
    val = frappe.db.sql(
        """
        SELECT COALESCE(SUM(actual_qty), 0)
        FROM `tabStock Ledger Entry`
        WHERE batch_no = %s AND warehouse = %s AND is_cancelled = 0
        """,
        (batch_no, warehouse),
    )
    return flt(val[0][0]) if val else 0.0


def _yarn_available_for_lot(root_lot, base_yarn_item, warehouse):
    """Sum balance of all batches of this lot whose base item == base_yarn_item."""
    batches = frappe.get_all(
        "Batch", filters={"custom_root_lot": root_lot}, fields=["name", "item"]
    )
    total = 0.0
    for b in batches:
        if resolver.extract_base_yarn_item(b.item) == base_yarn_item:
            total += _batch_balance_in_wh(b.name, warehouse)
    return total
