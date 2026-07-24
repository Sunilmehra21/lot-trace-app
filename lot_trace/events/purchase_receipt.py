# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Purchase Receipt handler (canonical).
# This file replaces BOTH the old Phase 5/6 purchase_receipt.py and the V2 file.
# It keeps every hook name the site's hooks.py might reference (before_submit,
# on_submit, on_cancel, before_cancel) so no AttributeError is possible.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2
from lot_trace.events import lot_factory_v2


# ---------------------------------------------------------------------------
# Hook entry points (all present — fixes Bug 2: "no attribute 'on_submit'")
# ---------------------------------------------------------------------------

def before_submit(doc, method=None):
    """Assign batch numbers and create/reuse Root Lots before stock posts."""
    greige_rows = []
    weave_rows = []

    for row in doc.items:
        rule, yarn_row = resolver_v2.find_naming_rule_for_item(row.item_code)
        if rule:
            greige_rows.append((row, rule, yarn_row))
        elif _is_weaving_output(row.item_code):
            weave_rows.append(row)

    if greige_rows:
        _handle_greige_intake(doc, greige_rows)
    for row in weave_rows:
        _handle_weaving_row(doc, row)


def on_submit(doc, method=None):
    """Kept for compatibility with hooks.py entries that reference on_submit.
    All work is done in before_submit (so batch_no is set before stock posts)."""
    pass


def before_cancel(doc, method=None):
    """Fixes Bug 1 (cancel deadlock): tell Frappe to skip the link check
    against our own tracking doctypes. on_cancel then cleans our records."""
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = ["Root Lot", "Batch", "Lot Receipt"]


def on_cancel(doc, method=None):
    """Remove Lot Receipt rows recorded by this PR and re-open intake."""
    seen_lots = set()
    for row in doc.items:
        if not row.get("batch_no"):
            continue
        rl = frappe.db.get_value("Batch", row.batch_no, "custom_root_lot")
        if rl:
            seen_lots.add(rl)

    for rl in seen_lots:
        if not frappe.db.exists("Root Lot", rl):
            continue
        lot = frappe.get_doc("Root Lot", rl)
        receipts = lot.get("lot_receipts", []) or []
        kept = [r for r in receipts if r.source_doc != doc.name]
        if len(kept) != len(receipts):
            lot.set("lot_receipts", kept)
            lot.intake_complete = 0
            lot.flags.ignore_links = True
            lot.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Greige intake
# ---------------------------------------------------------------------------

def _handle_greige_intake(doc, greige_rows):
    po_root_lot = _po_root_lot(doc)

    by_rule = {}
    for row, rule, yarn_row in greige_rows:
        by_rule.setdefault(rule, []).append((row, yarn_row))

    for rule, rows in by_rule.items():
        primary_present = any((yr or {}).get("role") == "Primary" for _, yr in rows)

        if primary_present:
            root_lot = lot_factory_v2.create_root_lot(rule)
        else:
            root_lot = _resolve_secondary_only_lot(rule, rows, po_root_lot)

        for row, yarn_row in rows:
            _attach_nt_batch(doc, row, root_lot, yarn_row)


def _resolve_secondary_only_lot(rule, rows, po_root_lot):
    first_item = rows[0][0].item_code
    decision = resolver_v2.resolve_open_lot(first_item, po_root_lot=po_root_lot)

    if decision["action"] == "reuse":
        if decision["ambiguous"]:
            frappe.throw(
                f"Multiple open lots are waiting for {first_item}. "
                f"Link the Purchase Order to a specific Root Lot first."
            )
        return decision["root_lot"]

    frappe.throw(
        f"{first_item} is a secondary yarn, but no open lot is waiting for it. "
        f"Receive the primary yarn first."
    )


def _attach_nt_batch(doc, row, root_lot, yarn_row):
    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
    abbr = (yarn_row or {}).get("item_abbr")
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
# Weaving output (restored — was dropped in the V2 file by mistake)
# ---------------------------------------------------------------------------

def _is_weaving_output(item_code):
    return bool(frappe.db.exists(
        "Lot Naming Rule", {"product": item_code, "active": 1}
    ))


def _handle_weaving_row(doc, row):
    rule = frappe.db.get_value(
        "Lot Naming Rule", {"product": row.item_code, "active": 1}, "name"
    )
    root_lot = _lot_at_supplier_for_rule(rule, doc.supplier)
    if not root_lot:
        frappe.throw(
            f"Could not resolve which lot's dyed yarn is with {doc.supplier} "
            f"for {row.item_code}. Set the Root Lot manually on this row."
        )
    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
    batch_name = resolver_v2.render_batch_name(lot_code, "WV")
    lot_factory_v2.ensure_batch(batch_name, row.item_code, root_lot, stage="WV")
    row.batch_no = batch_name
    frappe.db.set_value("Root Lot", root_lot, "current_stage", "WV")


def _lot_at_supplier_for_rule(rule, supplier):
    """Oldest open lot of this rule whose DY batches have stock at the
    supplier warehouse; falls back to the single open DY-stage lot."""
    open_lots = frappe.get_all(
        "Root Lot",
        filters={"naming_rule": rule, "status": ["!=", "Completed"]},
        fields=["name", "current_stage"],
        order_by="creation asc",
    )
    wh = _supplier_warehouse(supplier)
    if wh:
        for lot in open_lots:
            dy = frappe.get_all(
                "Batch",
                filters={"custom_root_lot": lot.name, "custom_stage": "DY"},
                pluck="name",
            )
            for b in dy:
                if _batch_balance_in_wh(b, wh) > 0.001:
                    return lot.name
    dy_lots = [l for l in open_lots if l.current_stage == "DY"]
    if len(dy_lots) == 1:
        return dy_lots[0].name
    if len(open_lots) == 1:
        return open_lots[0].name
    return None


def _supplier_warehouse(supplier):
    wh = frappe.db.get_value(
        "Warehouse", {"custom_supplier": supplier, "is_group": 0}, "name"
    )
    if wh:
        return wh
    return frappe.db.get_value(
        "Warehouse", {"warehouse_name": ["like", f"%{supplier}%"], "is_group": 0},
        "name",
    )


def _batch_balance_in_wh(batch_no, warehouse):
    val = frappe.db.sql(
        """SELECT COALESCE(SUM(actual_qty), 0)
           FROM `tabStock Ledger Entry`
           WHERE batch_no = %s AND warehouse = %s AND is_cancelled = 0""",
        (batch_no, warehouse),
    )
    return flt(val[0][0]) if val else 0.0


def _po_root_lot(doc):
    for row in doc.items:
        po = row.get("purchase_order")
        if po:
            rl = frappe.db.get_value("Purchase Order", po, "custom_root_lot")
            if rl:
                return rl
    return None
