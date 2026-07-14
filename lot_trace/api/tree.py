# Trace tree API: builds the full stage-chain of a Root Lot from native
# Batch records + Stock Ledger Entries. Powers the Lot Trace Tree page.

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_trace_tree(root_lot):
    """Return the Root Lot header + ordered stage nodes with movements.

    Nodes are returned in FORWARD stage order (NT -> FG); the page can
    render them forward or backward.
    """
    frappe.has_permission("Root Lot", "read", throw=True)
    if not root_lot or not frappe.db.exists("Root Lot", root_lot):
        frappe.throw(_("Root Lot {0} not found").format(root_lot))

    lot = frappe.db.get_value(
        "Root Lot", root_lot,
        ["name", "product", "supplier", "sales_order", "received_qty",
         "uom", "current_stage", "fg_qty", "dispatched_qty", "status"],
        as_dict=True)
    lot["open_exceptions"] = frappe.db.count(
        "Lot Exception", {"root_lot": root_lot, "resolved": 0})

    # all stage batches of this lot, in process sequence
    batches = frappe.db.sql("""
        SELECT b.name AS batch, b.item, b.process_stage,
               s.stage_name, s.sequence, s.expected_loss_pct
        FROM `tabBatch` b
        LEFT JOIN `tabLot Process Stage` s ON s.name = b.process_stage
        WHERE b.root_lot = %s
        ORDER BY s.sequence, b.name
    """, root_lot, as_dict=True)

    nodes = []
    for b in batches:
        movements = frappe.db.sql("""
            SELECT sle.posting_date, sle.voucher_type, sle.voucher_no,
                   sle.actual_qty, sle.qty_after_transaction, sle.warehouse,
                   sle.stock_uom
            FROM `tabStock Ledger Entry` sle
            WHERE sle.batch_no = %s AND sle.is_cancelled = 0
            ORDER BY sle.posting_date, sle.posting_time, sle.name
        """, b.batch, as_dict=True)

        in_qty = sum(flt(m.actual_qty) for m in movements if flt(m.actual_qty) > 0)
        out_qty = sum(abs(flt(m.actual_qty)) for m in movements if flt(m.actual_qty) < 0)
        uom = movements[0].stock_uom if movements else ""

        nodes.append({
            "batch": b.batch,
            "suffix": b.batch.replace(root_lot + "-", "", 1),
            "stage": b.process_stage,
            "stage_name": b.stage_name or b.process_stage,
            "sequence": b.sequence or 0,
            "expected_loss_pct": flt(b.expected_loss_pct),
            "item": b.item,
            "item_name": frappe.db.get_value("Item", b.item, "item_name") or b.item,
            "uom": uom,
            "in_qty": round(in_qty, 2),
            "out_qty": round(out_qty, 2),
            "balance": round(in_qty - out_qty, 2),
            "movements": [{
                "date": str(m.posting_date),
                "voucher_type": m.voucher_type,
                "voucher_no": m.voucher_no,
                "qty": flt(m.actual_qty),
                "warehouse": m.warehouse,
            } for m in movements],
        })

    return {"lot": lot, "nodes": nodes}
