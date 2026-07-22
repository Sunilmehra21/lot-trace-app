# -*- coding: utf-8 -*-
# Stock Entry hooks.
# - Send to Subcontractor / Material Issue / Transfer: enforce single lot.
# - Manufacture: validate inputs vs Work Order's root lot, create FG batch.

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events import common, lot_factory

FG_STAGE = "FG"


def before_submit(doc, method=None):
    lots = common.collect_root_lots(doc)
    common.enforce_single_lot(doc, lots)

    if doc.purpose == "Manufacture":
        _handle_manufacture(doc, lots)


def _handle_manufacture(doc, lots):
    wo_lot = None
    if doc.get("work_order"):
        wo_lot = frappe.db.get_value(
            "Work Order", doc.work_order, "root_lot")

    input_lot = sorted(lots)[0] if lots else None
    root_lot = wo_lot or input_lot

    if wo_lot and input_lot and wo_lot != input_lot:
        frappe.throw(_(
            "Work Order {0} is for root lot {1}, but the consumed batches "
            "belong to lot {2}. Use matching material or correct the Work "
            "Order.").format(doc.work_order, wo_lot, input_lot))

    if not root_lot:
        common.log_exception(
            "Missing Root Lot", "Warning",
            erp_doc_type=doc.doctype, erp_doc_name=doc.name,
            message=_("Manufacture entry has no root lot on inputs or "
                      "Work Order — finished goods are untraced."))
        return

    lot_code = frappe.db.get_value(
        "Root Lot", root_lot, "lot_code") or root_lot
    for row in doc.items:
        if row.get("is_finished_item") and not row.get("batch_no"):
            row.batch_no = common.create_stage_batch(
                lot_code, FG_STAGE, row.item_code)

    doc.flags.lot_trace_lot = root_lot
    doc.flags.lot_trace_input_qty = sum(
        flt(r.qty) for r in doc.items if not r.get("is_finished_item"))
    doc.flags.lot_trace_output_qty = sum(
        flt(r.qty) for r in doc.items if r.get("is_finished_item"))


def on_submit(doc, method=None):
    root_lot = doc.flags.get("lot_trace_lot")
    if root_lot:
        lot_factory.recompute_totals(root_lot)
        if doc.purpose == "Manufacture":
            common.check_stage_loss(
                root_lot=root_lot,
                stage_code=FG_STAGE,
                input_qty=doc.flags.get("lot_trace_input_qty", 0),
                output_qty=doc.flags.get("lot_trace_output_qty", 0),
                erp_doc_type=doc.doctype,
                erp_doc_name=doc.name,
            )


def on_cancel(doc, method=None):
    batches = [i.batch_no for i in doc.items if i.get("batch_no")]
    lot_factory.recompute_for_batches(batches)
