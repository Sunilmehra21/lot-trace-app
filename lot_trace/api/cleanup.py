# -*- coding: utf-8 -*-
# Phase 6.3 — Root Lot deletion with cleanup.
#
# Root Lot is NOT a submittable doctype, so there is no Cancel button on it —
# delete is the correct action. But Frappe's link check blocks the delete
# because batches / receipt rows reference the lot (and the PR side pointed
# back), creating the deadlock the user hit. This API breaks the cycle in the
# right order: detach batches -> clear receipt rows -> force-delete the lot.
#
# It never deletes stock documents (PR/SR) or batches themselves — those stay,
# only OUR links are removed. Cancel/delete the PRs separately if needed
# (the before_cancel hook now allows that).

import frappe


@frappe.whitelist()
def delete_root_lot(root_lot):
    """Delete a Root Lot after detaching everything that references it."""
    if not frappe.has_permission("Root Lot", "delete"):
        frappe.throw("Not permitted to delete Root Lots.")
    if not frappe.db.exists("Root Lot", root_lot):
        frappe.throw(f"Root Lot {root_lot} not found.")

    # 1) Detach batches (kept — they may hold posted stock).
    batches = frappe.get_all(
        "Batch", filters={"custom_root_lot": root_lot}, pluck="name"
    )
    for b in batches:
        frappe.db.set_value("Batch", b, {
            "custom_root_lot": None,
            "custom_stage": None,
        }, update_modified=False)

    # 2) Clear back-references on stock documents that point at this lot.
    for dt, field in [
        ("Purchase Order", "custom_root_lot"),
        ("Subcontracting Receipt Item", "custom_root_lot"),
    ]:
        if frappe.get_meta(dt).get_field(field):
            frappe.db.sql(
                f"UPDATE `tab{dt}` SET {field} = NULL WHERE {field} = %s",
                (root_lot,),
            )

    # 3) Delete the lot. force=1 skips the link check (we just cleaned up);
    #    child Lot Receipt rows are deleted automatically with the parent.
    frappe.delete_doc("Root Lot", root_lot, force=1, ignore_permissions=True)

    return {
        "deleted": root_lot,
        "batches_detached": len(batches),
        "message": f"Root Lot {root_lot} deleted. {len(batches)} batch(es) "
                   f"detached (batches and stock documents are kept).",
    }
