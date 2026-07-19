# -*- coding: utf-8 -*-
# Phase 6 V2 — Lot Factory (simplified)
# Creates Root Lot, Batch, and Lot Receipt records.

import frappe
from frappe.utils import flt, nowdate

from lot_trace.events import resolver_v2
from lot_trace.lot_trace.doctype.lot_naming_rule.lot_naming_rule import generate_lot_code


def create_root_lot(rule_name):
    """Create a NEW Root Lot for this rule (primary yarn received)."""
    lot_code = generate_lot_code(rule_name)
    mmyy = nowdate().strftime("%m%y")
    serial = int(lot_code.split("/")[-1])  # extract serial from code
    product = resolver_v2.get_product_for_rule(rule_name)

    doc = frappe.get_doc({
        "doctype": "Root Lot",
        "lot_code": lot_code,
        "naming_rule": rule_name,
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
    """Create Batch record (idempotent)."""
    if frappe.db.exists("Batch", batch_name):
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
    """Record per-item received qty in Lot Receipt child table."""
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
    """Mark intake_complete when all yarns have been received."""
    rule = rl_doc.naming_rule
    if not rule:
        return
    all_yarns = resolver_v2.get_all_yarns_for_rule(rule)
    received = {r.yarn_item for r in rl_doc.get("lot_receipts", [])}
    all_items = {y["yarn_item"] for y in all_yarns}
    if all_items and all_items.issubset(received):
        rl_doc.intake_complete = 1
