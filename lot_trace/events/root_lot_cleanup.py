# -*- coding: utf-8 -*-
# V7 — Root Lot cancel/delete cleanup (breaks circular link checks).

import frappe


def before_cancel(doc, method=None):
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = [
        "Purchase Receipt", "Subcontracting Receipt", "Batch", "Lot Receipt"]


def on_trash(doc, method=None):
    # Detach batches — they may hold posted stock, so they are KEPT.
    for b in frappe.get_all(
            "Batch", filters={"custom_root_lot": doc.name}, pluck="name"):
        frappe.db.set_value("Batch", b, {
            "custom_root_lot": None, "custom_stage": None,
        }, update_modified=False)
