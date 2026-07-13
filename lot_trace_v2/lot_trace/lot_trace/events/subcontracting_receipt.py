# Subcontracting Receipt: inherit root lot from consumed supplied batches,
# auto-create the output stage batch, check stage loss.

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events.common import (
    check_stage_loss, create_stage_batch, enforce_single_lot,
    get_root_lot_of_batch, log_exception, next_stage_after)


def before_submit(doc, method=None):
    # 1) which root lot did we consume?
    lots, input_qty, input_stage = set(), 0.0, None
    for rm in doc.get("supplied_items") or []:
        rl = get_root_lot_of_batch(rm.get("batch_no"))
        if rl:
            lots.add(rl)
            input_qty += flt(rm.get("consumed_qty"))
            input_stage = input_stage or frappe.db.get_value(
                "Batch", rm.batch_no, "process_stage")

    if not lots:
        log_exception("Missing Root Lot", "Warning",
                      erp_doc_type=doc.doctype, erp_doc_name=doc.name,
                      message=_("No root lot found on consumed supplied items - "
                                "receipt is untraced."))
        return

    enforce_single_lot(doc, lots)
    root_lot = sorted(lots)[0]

    # 2) output stage: SCO's lot_stage field, else next stage after input
    stage = None
    sco = doc.items[0].get("subcontracting_order") if doc.items else None
    if sco:
        stage = frappe.db.get_value("Subcontracting Order", sco, "lot_stage")
    if not stage and input_stage:
        stage = next_stage_after(input_stage)
    if not stage:
        frappe.throw(_("Cannot determine output Lot Stage: set 'Lot Stage' on the "
                       "Subcontracting Order."))

    # 3) create/assign output batch on received rows
    output_qty = 0.0
    for row in doc.items:
        if not row.get("batch_no"):
            row.batch_no = create_stage_batch(root_lot, stage, row.item_code)
        row.root_lot = root_lot
        output_qty += flt(row.qty)

    doc._lot_loss_args = (root_lot, stage, input_qty, output_qty)


def on_submit(doc, method=None):
    args = getattr(doc, "_lot_loss_args", None)
    if args:
        root_lot, stage, input_qty, output_qty = args
        # loss check only where input/output UOM comparable (e.g. DY: kg->kg)
        same_uom = len({(r.get("stock_uom") or "").lower() for r in doc.items} |
                       {(r.get("stock_uom") or "").lower()
                        for r in doc.get("supplied_items") or []}) == 1
        if same_uom:
            check_stage_loss(root_lot, stage, input_qty, output_qty,
                             erp_doc_type=doc.doctype, erp_doc_name=doc.name)
