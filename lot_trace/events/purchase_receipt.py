# -*- coding: utf-8 -*-
# Purchase Receipt hooks.
# Case A — greige yarn intake (item in an active Lot Naming Rule):
#   Primary yarn  -> new Root Lot
#   Secondary yarn-> FIFO reuse of oldest open lot missing that yarn
# Case B — weaving receipt against a lot-linked PO (lot_stage = WV):
#   -> WV batch on the linked Root Lot
# Never touches core stock/valuation logic (design P5).

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events import common, resolver, lot_factory


def before_submit(doc, method=None):
    plan = []
    for item in doc.items:
        # Case A — greige yarn intake
        rule, yarn_row = resolver.find_naming_rule_for_item(item.item_code)
        if rule:
            if item.get("batch_no"):
                continue  # user pre-assigned a batch manually
            decision = resolver.resolve_open_lot(item.item_code)
            if decision["action"] == "new":
                root_lot = lot_factory.create_root_lot(
                    rule, posting_date=doc.posting_date,
                    sales_order=doc.get("sales_order"))
            elif decision["action"] == "reuse":
                root_lot = decision["root_lot"]
            else:
                frappe.throw(_(
                    "{0} is a SECONDARY yarn and no open lot is waiting for "
                    "it. Receive the primary yarn first (that creates the "
                    "lot), then receive this one."
                ).format(item.item_code))

            lot_code = frappe.db.get_value(
                "Root Lot", root_lot, "lot_code") or root_lot
            batch_no = common.create_stage_batch(
                lot_code, common.first_stage_for_rule(rule),
                item.item_code, yarn_row.item_abbr)
            item.batch_no = batch_no
            item.root_lot = root_lot
            plan.append({
                "kind": "yarn", "root_lot": root_lot,
                "yarn_item": item.item_code,
                "item_abbr": yarn_row.item_abbr,
                "batch_no": batch_no,
                "received_kg": flt(item.stock_qty or item.qty),
                "supplier": doc.supplier,
            })
            continue

        # Case B — weaving receipt against a lot-linked PO
        po = item.get("purchase_order")
        if po and not item.get("batch_no"):
            po_stage = frappe.db.get_value("Purchase Order", po, "lot_stage")
            root_lot = frappe.db.get_value(
                "Purchase Order Item",
                {"parent": po, "item_code": item.item_code},
                "root_lot")
            if not root_lot:
                root_lot = frappe.db.get_value(
                    "Purchase Order", po, "root_lot")
            if root_lot and po_stage:
                lot_code = frappe.db.get_value(
                    "Root Lot", root_lot, "lot_code") or root_lot
                batch_no = common.create_stage_batch(
                    lot_code, po_stage, item.item_code)
                item.batch_no = batch_no
                item.root_lot = root_lot
                plan.append({
                    "kind": "stage",
                    "root_lot": root_lot,
                    "stage": po_stage,
                    "input_qty": flt(item.stock_qty or item.qty),
                    "output_item": item.item_code,
                })

    doc.flags.lot_trace_plan = plan


def on_submit(doc, method=None):
    for p in (doc.flags.get("lot_trace_plan") or []):
        if p["kind"] == "yarn":
            lot_factory.record_lot_receipt(
                root_lot=p["root_lot"],
                yarn_item=p["yarn_item"],
                item_abbr=p["item_abbr"],
                batch_no=p["batch_no"],
                received_kg=p["received_kg"],
                source_doctype="Purchase Receipt",
                source_doc=doc.name,
                supplier=p.get("supplier"),
            )
        elif p["kind"] == "stage":
            lot_factory.recompute_totals(p["root_lot"])
            common.check_stage_loss(
                root_lot=p["root_lot"],
                stage_code=p["stage"],
                input_qty=0,
                output_qty=p["input_qty"],
                erp_doc_type="Purchase Receipt",
                erp_doc_name=doc.name,
                output_item=p.get("output_item"),
            )


def before_cancel(doc, method=None):
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = ["Root Lot", "Batch", "Lot Receipt"]


def on_cancel(doc, method=None):
    lot_factory.remove_lot_receipts_for_source("Purchase Receipt", doc.name)
    batches = [i.batch_no for i in doc.items if i.get("batch_no")]
    lot_factory.recompute_for_batches(batches)
