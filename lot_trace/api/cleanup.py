# -*- coding: utf-8 -*-
# V7 — Root Lot deletion with cleanup (breaks the PR <-> lot deadlock).
# Root Lot is not submittable, so delete (not cancel) is the correct action.

import frappe


@frappe.whitelist()
def delete_root_lot(root_lot):
    if not frappe.has_permission("Root Lot", "delete"):
        frappe.throw("Not permitted to delete Root Lots.")
    if not frappe.db.exists("Root Lot", root_lot):
        frappe.throw(f"Root Lot {root_lot} not found.")

    batches = frappe.get_all(
        "Batch", filters={"custom_root_lot": root_lot}, pluck="name")
    for b in batches:
        frappe.db.set_value("Batch", b, {
            "custom_root_lot": None, "custom_stage": None,
        }, update_modified=False)

    for dt, field in [("Purchase Order", "custom_root_lot"),
                      ("Subcontracting Receipt Item", "custom_root_lot")]:
        if frappe.get_meta(dt).get_field(field):
            frappe.db.sql(
                f"UPDATE `tab{dt}` SET {field} = NULL WHERE {field} = %s",
                (root_lot,))

    frappe.delete_doc("Root Lot", root_lot, force=1, ignore_permissions=True)
    return {
        "deleted": root_lot,
        "batches_detached": len(batches),
        "message": f"Root Lot {root_lot} deleted. {len(batches)} batch(es) "
                   f"detached (batches and stock documents are kept).",
    }
