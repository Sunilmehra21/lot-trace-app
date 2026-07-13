# Delivery Note / Sales Invoice:
#  - require dispatch_type when rows carry root-lot batches
#  - Final dispatch: track dispatched qty, complete the Root Lot
#  - Intermediate dispatch (dyed yarn to weaver): nothing to do beyond native
#    batch selection - the At-Weaver Balance report reads it from SLE.

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events.common import (
    collect_root_lots, enforce_single_lot, get_root_lot_of_batch)


def is_stock_effective(doc):
    return doc.doctype == "Delivery Note" or doc.get("update_stock")


def before_submit(doc, method=None):
    if not is_stock_effective(doc) or doc.get("is_return"):
        return
    lots = collect_root_lots(doc)
    if lots and not doc.get("dispatch_type"):
        frappe.throw(_(
            "This document dispatches traced lot material ({0}). "
            "Set Dispatch Type = Intermediate (to weaver) or Final (to end customer)."
        ).format(", ".join(sorted(lots))))
    enforce_single_lot(doc, lots)


def on_submit(doc, method=None):
    if not is_stock_effective(doc):
        return
    sign = -1 if doc.get("is_return") else 1
    if doc.get("dispatch_type") != "Final" and not doc.get("is_return"):
        return
    for row in doc.items:
        rl = get_root_lot_of_batch(row.get("batch_no"))
        if not rl:
            continue
        stage = frappe.db.get_value("Batch", row.batch_no, "process_stage")
        if stage != "FG":
            continue
        lot = frappe.get_doc("Root Lot", rl)
        lot.dispatched_qty = flt(lot.dispatched_qty) + sign * flt(row.qty)
        if flt(lot.fg_qty) and lot.dispatched_qty >= flt(lot.fg_qty) - 1e-6:
            lot.status = "Completed"
        elif lot.status == "Completed":
            lot.status = "In Process"
        lot.flags.ignore_permissions = True
        lot.save()


def on_cancel(doc, method=None):
    if not is_stock_effective(doc) or doc.get("dispatch_type") != "Final":
        return
    for row in doc.items:
        rl = get_root_lot_of_batch(row.get("batch_no"))
        if not rl:
            continue
        stage = frappe.db.get_value("Batch", row.batch_no, "process_stage")
        if stage != "FG":
            continue
        lot = frappe.get_doc("Root Lot", rl)
        lot.dispatched_qty = flt(lot.dispatched_qty) - flt(row.qty)
        if lot.status == "Completed":
            lot.status = "In Process"
        lot.flags.ignore_permissions = True
        lot.save()
