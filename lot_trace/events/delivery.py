# -*- coding: utf-8 -*-
# Delivery Note / Sales Invoice hooks.
# - Require dispatch_type when rows carry root-lot batches.
# - Final dispatch: recompute dispatched_qty + mark lot Completed.
# - Intermediate dispatch (dyed yarn to weaver): no action needed beyond
#   native batch selection — At-Weaver Balance reads it from SLE.

import frappe
from frappe import _

from lot_trace.events import common, lot_factory


def _is_stock_effective(doc):
    return doc.doctype == "Delivery Note" or doc.get("update_stock")


def before_submit(doc, method=None):
    if not _is_stock_effective(doc) or doc.get("is_return"):
        return
    lots = common.collect_root_lots(doc)
    if lots and not doc.get("dispatch_type"):
        frappe.throw(_(
            "This document dispatches traced lot material ({0}). "
            "Set Dispatch Type = Intermediate (to weaver) or Final "
            "(to end customer).").format(", ".join(sorted(lots))))
    common.enforce_single_lot(doc, lots)


def on_submit(doc, method=None):
    if not _is_stock_effective(doc):
        return
    if doc.get("dispatch_type") != "Final" and not doc.get("is_return"):
        return
    batches = [i.batch_no for i in doc.items if i.get("batch_no")]
    lot_factory.recompute_for_batches(batches)


def on_cancel(doc, method=None):
    if not _is_stock_effective(doc):
        return
    batches = [i.batch_no for i in doc.items if i.get("batch_no")]
    lot_factory.recompute_for_batches(batches)
