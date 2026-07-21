# -*- coding: utf-8 -*-
# V7 — Purchase Receipt hooks.
# Case A (yarn intake): item is a greige yarn in an active rule ->
#   Primary yarn = new lot; Secondary = FIFO reuse. Sets item.batch_no only.
# Case B (weaving): PR against a Purchase Order that carries custom_root_lot
#   -> WV batch on that lot.
# Never touches core stock/valuation logic (requirement #4).

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2, lot_factory_v2


def before_submit(doc, method=None):
    plan = []
    for item in doc.items:
        # Case A — greige yarn intake
        rule, yarn_row = resolver_v2.find_naming_rule_for_item(item.item_code)
        if rule:
            if item.get("batch_no"):
                continue  # user already assigned a lot batch manually
            decision = resolver_v2.resolve_open_lot(item.item_code)
            if decision["action"] == "new":
                root_lot = lot_factory_v2.create_root_lot(rule)
            elif decision["action"] == "reuse":
                root_lot = decision["root_lot"]
            else:  # blocked: secondary yarn, nothing waiting for it
                frappe.throw(
                    f"{item.item_code} is a SECONDARY yarn and no open lot "
                    f"is waiting for it. Receive the primary yarn first "
                    f"(that creates the lot), then receive this one.")
            lot_code = frappe.db.get_value(
                "Root Lot", root_lot, "lot_code") or root_lot
            batch = resolver_v2.render_batch_name(
                lot_code, "NT", abbr=yarn_row.item_abbr)
            lot_factory_v2.ensure_batch(batch, item.item_code, root_lot, "NT")
            item.batch_no = batch
            plan.append({
                "kind": "yarn", "root_lot": root_lot,
                "yarn_item": item.item_code,
                "item_abbr": yarn_row.item_abbr, "nt_batch": batch,
                "received_kg": flt(item.stock_qty or item.qty),
            })
            continue

        # Case B — weaving receipt against a lot-linked PO
        po = item.get("purchase_order")
        if po and not item.get("batch_no"):
            root_lot = frappe.db.get_value(
                "Purchase Order", po, "custom_root_lot")
            if root_lot:
                lot_code = frappe.db.get_value(
                    "Root Lot", root_lot, "lot_code") or root_lot
                batch = resolver_v2.render_batch_name(lot_code, "WV")
                lot_factory_v2.ensure_batch(
                    batch, item.item_code, root_lot, "WV")
                item.batch_no = batch
                plan.append({"kind": "wv", "root_lot": root_lot})

    doc.flags.lot_trace_plan = plan


def on_submit(doc, method=None):
    for p in (doc.flags.get("lot_trace_plan") or []):
        if p["kind"] == "yarn":
            lot_factory_v2.record_lot_receipt(
                root_lot=p["root_lot"],
                yarn_item=p["yarn_item"],
                item_abbr=p["item_abbr"],
                nt_batch=p["nt_batch"],
                received_kg=p["received_kg"],
                source_doctype="Purchase Receipt",
                source_doc=doc.name,
            )
        elif p["kind"] == "wv":
            lot_factory_v2.set_current_stage(p["root_lot"], "WV")
            lot_factory_v2.recompute_totals(p["root_lot"])


def before_cancel(doc, method=None):
    # break the PR <-> Root Lot circular link check
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = ["Root Lot", "Batch", "Lot Receipt"]


def on_cancel(doc, method=None):
    lot_factory_v2.remove_lot_receipts_for_source(
        "Purchase Receipt", doc.name)
    # refresh totals on any lot whose batches this PR touched
    lots = {frappe.db.get_value("Batch", i.batch_no, "custom_root_lot")
            for i in doc.items if i.get("batch_no")}
    for lot in filter(None, lots):
        lot_factory_v2.recompute_totals(lot)
