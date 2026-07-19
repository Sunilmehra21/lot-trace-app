# -*- coding: utf-8 -*-
# Phase 6 — Lot Factory
# The ONLY place that creates Root Lot and Batch documents and records receipts.
# Centralised so naming/serial/period logic stays consistent everywhere.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver


def create_root_lot(profile_name, po_root_lot=None):
    """Create a NEW Root Lot for a production run of this profile.

    Increments the per-profile, per-month serial. Returns the Root Lot name.
    This is called ONLY when the primary yarn is received (a new run begins).
    """
    serial = resolver.next_lot_serial(profile_name)
    mmyy = resolver.nowdate_mmyy()
    pattern = frappe.db.get_value("Lot Trace Profile", profile_name, "lot_code_pattern")
    lot_code = resolver._render_lot_code(pattern, serial)
    product = frappe.db.get_value("Lot Trace Profile", profile_name, "product")

    doc = frappe.get_doc({
        "doctype": "Root Lot",
        "lot_code": lot_code,
        "profile": profile_name,
        "product": product,
        "serial": serial,
        "period_mmyy": mmyy,
        "current_stage": "NT",
        "intake_complete": 0,
        "status": "Open",
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def ensure_batch(batch_name, item_code, root_lot, stage):
    """Create a Batch (if absent) linked to the root lot + stage.

    Only creates the Batch master record. Stock is posted by standard ERP when
    the parent voucher submits with this batch_no on the row.
    """
    if frappe.db.exists("Batch", batch_name):
        # Ensure our custom links are present (idempotent).
        frappe.db.set_value("Batch", batch_name, {
            "custom_root_lot": root_lot,
            "custom_stage": stage,
        })
        return batch_name

    batch = frappe.get_doc({
        "doctype": "Batch",
        "batch_id": batch_name,
        "item": item_code,
        "custom_root_lot": root_lot,
        "custom_stage": stage,
    })
    batch.insert(ignore_permissions=True)
    return batch.name


def record_lot_receipt(root_lot, yarn_item, item_abbr, nt_batch, received_kg,
                       source_doctype, source_doc):
    """Append a Lot Receipt row on the Root Lot (per-item received qty).

    Idempotent per (yarn_item, source_doc): re-submitting won't duplicate.
    """
    rl = frappe.get_doc("Root Lot", root_lot)
    for r in rl.get("lot_receipts", []):
        if r.yarn_item == yarn_item and r.source_doc == source_doc:
            return  # already recorded

    rl.append("lot_receipts", {
        "yarn_item": yarn_item,
        "item_abbr": item_abbr,
        "nt_batch": nt_batch,
        "received_kg": flt(received_kg),
        "source_doctype": source_doctype,
        "source_doc": source_doc,
    })
    _refresh_intake_complete(rl)
    rl.save(ignore_permissions=True)


def _refresh_intake_complete(rl_doc):
    """Mark intake_complete once every profile yarn has an NT receipt."""
    profile_items = frappe.get_all(
        "Lot Trace Item", filters={"parent": rl_doc.profile}, pluck="yarn_item"
    )
    received = {r.yarn_item for r in rl_doc.get("lot_receipts", [])}
    if profile_items and set(profile_items).issubset(received):
        rl_doc.intake_complete = 1
