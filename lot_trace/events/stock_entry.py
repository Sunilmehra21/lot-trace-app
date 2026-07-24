# Stock Entry:
#  - Send to Subcontractor / Material Issue / Transfer: enforce single root lot
#  - Manufacture: validate inputs vs Work Order's root lot, create '-FG' batch

import frappe
from frappe import _

from lot_trace.events.common import (
    collect_root_lots, create_stage_batch, enforce_single_lot,
    get_root_lot_of_batch, log_exception)

FG_STAGE = "FG"


def before_submit(doc, method=None):
    lots = collect_root_lots(doc)
    enforce_single_lot(doc, lots)

    if doc.purpose == "Manufacture":
        handle_manufacture(doc, lots)


def handle_manufacture(doc, lots):
    wo_lot = None
    if doc.get("work_order"):
        wo_lot = frappe.db.get_value("Work Order", doc.work_order, "root_lot")

    input_lot = sorted(lots)[0] if lots else None
    root_lot = wo_lot or input_lot

    if wo_lot and input_lot and wo_lot != input_lot:
        frappe.throw(_(
            "Work Order {0} is for root lot {1}, but the consumed batches belong "
            "to lot {2}. Use matching material or correct the Work Order."
        ).format(doc.work_order, wo_lot, input_lot))

    if not root_lot:
        log_exception("Missing Root Lot", "Warning",
                      erp_doc_type=doc.doctype, erp_doc_name=doc.name,
                      message=_("Manufacture entry has no root lot on inputs or "
                                "Work Order - finished goods are untraced."))
        return

    for row in doc.items:
        if row.get("is_finished_item") and not row.get("batch_no"):
            row.batch_no = create_stage_batch(root_lot, FG_STAGE, row.item_code)
            # accumulate FG qty on the lot
            frappe.db.set_value(
                "Root Lot", root_lot, "fg_qty",
                (frappe.db.get_value("Root Lot", root_lot, "fg_qty") or 0)
                + (row.qty or 0), update_modified=False)
