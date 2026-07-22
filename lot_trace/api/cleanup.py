# -*- coding: utf-8 -*-
# Root Lot deletion with cleanup (Root Lot is not submittable, so delete —
# not cancel — is the correct removal action).

import frappe
from frappe import _


@frappe.whitelist()
def delete_root_lot(root_lot):
    if not frappe.has_permission("Root Lot", "delete"):
        frappe.throw(_("Not permitted to delete Root Lots."),
                     frappe.PermissionError)
    if not frappe.db.exists("Root Lot", root_lot):
        frappe.throw(_("Root Lot {0} not found.").format(root_lot))

    # detach batches (they may hold posted stock — always KEPT)
    batches = frappe.get_all(
        "Batch", filters={"root_lot": root_lot}, pluck="name")
    for b in batches:
        frappe.db.set_value("Batch", b, {
            "root_lot": None, "process_stage": None,
        }, update_modified=False)

    # clear back-references on core documents
    for dt, field in [("Purchase Order Item", "root_lot"),
                      ("Purchase Order", "root_lot"),
                      ("Purchase Receipt Item", "root_lot"),
                      ("Subcontracting Receipt Item", "root_lot"),
                      ("Work Order", "root_lot")]:
        meta = frappe.get_meta(dt)
        if meta.get_field(field):
            frappe.db.sql(
                "UPDATE `tab{0}` SET {1} = NULL WHERE {1} = %s".format(
                    dt, field), (root_lot,))

    frappe.delete_doc("Root Lot", root_lot, force=1, ignore_permissions=True)
    return {
        "deleted": root_lot,
        "batches_detached": len(batches),
        "message": _(
            "Root Lot {0} deleted. {1} batch(es) detached (batches and "
            "stock documents are kept)."
        ).format(root_lot, len(batches)),
    }
