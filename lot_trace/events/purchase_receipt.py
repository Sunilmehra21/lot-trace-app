# Purchase Receipt:
#  A) greige yarn from spinner  -> LOT BIRTH: create Root Lot + '-NT' batch
#  B) weaved pcs from weaver    -> BRIDGE: root_lot mandatory on row -> '-WV' batch

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events.common import (
    create_stage_batch, find_naming_rule, log_exception, make_lot_code)

FIRST_STAGE = "NT"
WEAVE_STAGE = "WV"


def before_submit(doc, method=None):
    if doc.is_return:
        return
    for row in doc.items:
        if row.get("batch_no"):
            continue

        # B) weaved pcs bridge --------------------------------------------
        if is_weaving_row(row):
            if not row.get("root_lot"):
                frappe.throw(_(
                    "Row {0} ({1}): Root Lot is mandatory for weaved pcs receipts. "
                    "Select which lot's dyed yarn these pieces were woven from."
                ).format(row.idx, row.item_code))
            validate_lot_reached_weaver(row.root_lot, row.idx)
            row.batch_no = create_stage_batch(row.root_lot, WEAVE_STAGE, row.item_code)
            continue

        # A) yarn lot birth ------------------------------------------------
        rule = find_naming_rule(yarn_item=row.item_code)
        if not rule:
            continue  # not a traced item
        lot_code = make_lot_code(rule, doc.posting_date)
        create_root_lot(doc, row, rule, lot_code)
        row.batch_no = create_stage_batch(lot_code, FIRST_STAGE, row.item_code)
        row.root_lot = lot_code


def is_weaving_row(row):
    if not row.get("purchase_order"):
        return False
    return frappe.db.get_value(
        "Purchase Order", row.purchase_order, "lot_stage") == WEAVE_STAGE


def validate_lot_reached_weaver(root_lot, idx):
    if not frappe.db.exists("Root Lot", root_lot):
        frappe.throw(_("Row {0}: Root Lot {1} does not exist").format(idx, root_lot))
    dy_batch = frappe.db.get_value(
        "Batch", {"root_lot": root_lot, "process_stage": "DY"})
    if not dy_batch:
        frappe.throw(_(
            "Row {0}: Root Lot {1} has no dyed-yarn (DY) batch yet - "
            "it cannot have weaved pcs.").format(idx, root_lot))


def create_root_lot(doc, row, rule, lot_code):
    lot = frappe.new_doc("Root Lot")
    lot.update({
        "lot_code": lot_code,
        "product": rule.product,
        "yarn_item": row.item_code,
        "sales_order": rule.get("sales_order"),
        "supplier": doc.supplier,
        "supplier_invoice": doc.get("supplier_delivery_note") or doc.get("bill_no"),
        "purchase_receipt": doc.name,
        "received_qty": flt(row.qty),
        "uom": row.uom,
        "current_stage": FIRST_STAGE,
        "status": "Open",
    })
    lot.flags.ignore_permissions = True
    lot.insert()


def on_submit(doc, method=None):
    if not doc.is_return:
        return
    # purchase return of yarn: reflect on Root Lot received qty
    for row in doc.items:
        rl = row.get("root_lot") or frappe.db.get_value(
            "Batch", row.get("batch_no"), "root_lot")
        if rl:
            frappe.db.set_value(
                "Root Lot", rl, "received_qty",
                flt(frappe.db.get_value("Root Lot", rl, "received_qty"))
                - abs(flt(row.qty)), update_modified=False)


def on_cancel(doc, method=None):
    if doc.is_return:
        return
    for row in doc.items:
        rl = row.get("root_lot")
        if not rl or not frappe.db.exists("Root Lot", rl):
            continue
        if frappe.db.get_value("Root Lot", rl, "purchase_receipt") != doc.name:
            continue
        # lot born from this PR: remove if untouched downstream
        other_batches = frappe.get_all(
            "Batch", filters={"root_lot": rl, "process_stage": ["!=", "NT"]}, pluck="name")
        if other_batches:
            log_exception("Cancel With Downstream", "Error", root_lot=rl,
                          erp_doc_type=doc.doctype, erp_doc_name=doc.name,
                          message=_("PR cancelled but lot {0} already has downstream "
                                    "batches: {1}").format(rl, ", ".join(other_batches)))
            continue
        nt_batch = f"{rl}-NT"
        sle = frappe.db.count("Stock Ledger Entry",
                              {"batch_no": nt_batch, "is_cancelled": 0})
        if not sle:
            frappe.delete_doc("Batch", nt_batch, ignore_permissions=True, force=True)
            frappe.delete_doc("Root Lot", rl, ignore_permissions=True, force=True)
        else:
            frappe.db.set_value("Root Lot", rl, "status", "Short Closed",
                                update_modified=False)
