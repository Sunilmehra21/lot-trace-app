# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Root Lot cancel/delete cleanup (Bug 1, Root Lot side).
#
# The deadlock: PR cancel was blocked by the Root Lot's link to it, and Root
# Lot cancel was blocked by its link to the PR. Neither side could go first.
# Fix: on the Root Lot side, skip the link check and clean up our own link
# records (batch back-references) so the lot can be cancelled/deleted.
#
# Wired via hooks doc_events on "Root Lot" (no doctype controller overwrite,
# so any existing Phase 5 root_lot.py logic is untouched).

import frappe


def before_cancel(doc, method=None):
    """Allow cancelling a Root Lot even though PRs/SRs/Batches reference it."""
    doc.flags.ignore_links = True
    doc.ignore_linked_doctypes = [
        "Purchase Receipt", "Subcontracting Receipt", "Batch", "Stock Entry",
    ]


def on_trash(doc, method=None):
    """Detach batches from this lot so deletion isn't blocked.

    Batches themselves are kept — they may hold stock posted by ERPNext.
    Only our back-reference (custom_root_lot) is cleared.
    """
    batches = frappe.get_all(
        "Batch", filters={"custom_root_lot": doc.name}, pluck="name"
    )
    for b in batches:
        frappe.db.set_value("Batch", b, {
            "custom_root_lot": None,
            "custom_stage": None,
        }, update_modified=False)

    if batches:
        frappe.msgprint(
            f"Detached {len(batches)} batch(es) from {doc.name}. "
            f"The batches still exist; only the lot link was removed.",
            alert=True,
        )
