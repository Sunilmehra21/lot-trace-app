# -*- coding: utf-8 -*-
# Root Lot cancel / delete cleanup.

import frappe


def before_cancel(doc, method=None):
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = [
        "Purchase Receipt", "Subcontracting Receipt", "Batch", "Lot Receipt"]


def on_trash(doc, method=None):
    """Detach batches when a Root Lot is deleted (batches are KEPT)."""
    for b in frappe.get_all(
            "Batch", filters={"root_lot": doc.name}, pluck="name"):
        frappe.db.set_value("Batch", b, {
            "root_lot": None, "process_stage": None,
        }, update_modified=False)
