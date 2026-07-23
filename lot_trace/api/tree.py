# -*- coding: utf-8 -*-
# Lot Trace Tree API: hierarchical view of a lot's batches and movements.
# Transfer double-count fix (Phase 3A5): a Material Transfer writes both a
# -qty and +qty SLE row for the SAME batch; if not netted this doubles the
# in/out totals shown in the tree ("received 800, issued 800 -> shows 0
# balance / 0 in DY stage" style bugs). We net same-voucher +/- pairs into a
# single "transfer" amount excluded from in/out, and surface separate
# in_qty/out_qty/transfer_qty per batch plus per-movement party + a
# tolerance-based loss badge (Phase 3A4/A6).

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events import common

# Same voucher-type -> party-field map used by the Root Lot Trace report.
SUPPLIER_VOUCHERS = {
    "Purchase Receipt": "supplier",
    "Purchase Invoice": "supplier",
    "Subcontracting Receipt": "supplier",
}
CUSTOMER_VOUCHERS = {
    "Delivery Note": "customer",
    "Sales Invoice": "customer",
}


def _party_for_voucher(voucher_type, voucher_no):
    fieldname = SUPPLIER_VOUCHERS.get(voucher_type) or CUSTOMER_VOUCHERS.get(voucher_type)
    if not fieldname or not voucher_no:
        return None
    if not frappe.db.has_column(voucher_type, fieldname):
        return None
    return frappe.db.get_value(voucher_type, voucher_no, fieldname)


@frappe.whitelist()
def get_lot_tree(root_lot):
    """Tree: Root Lot -> stage batches -> stock movements."""
    frappe.has_permission("Root Lot", "read", throw=True)
    if not root_lot:
        return {}

    lot = frappe.db.get_value(
        "Root Lot", root_lot,
        ["name", "lot_code", "product", "status", "current_stage",
         "received_qty", "uom", "fg_qty", "dispatched_qty", "weaved_pcs",
         "yarn_in_process_qty", "sales_order"],
        as_dict=True)
    if not lot:
        return {}

    batches = frappe.get_all(
        "Batch",
        filters={"root_lot": root_lot},
        fields=["name", "item", "process_stage"])

    stage_seq = {s.name: s.sequence for s in frappe.get_all(
        "Lot Process Stage", fields=["name", "sequence"])}
    batches.sort(key=lambda b: stage_seq.get(b.process_stage, 99))

    tol = flt(common.get_settings().weaving_tolerance_pct) or 0

    nodes = []
    prev_out_qty = None
    for b in batches:
        sle = frappe.db.sql("""
            SELECT voucher_type, voucher_no, actual_qty, stock_uom,
                   posting_date, warehouse
            FROM `tabStock Ledger Entry`
            WHERE batch_no = %s AND is_cancelled = 0
            ORDER BY posting_date, posting_time, name
        """, b.name, as_dict=True)

        # Group rows by voucher so a Material Transfer's +qty/-qty pair on
        # this SAME batch can be netted instead of double-counted.
        by_voucher = {}
        for m in sle:
            by_voucher.setdefault((m.voucher_type, m.voucher_no), []).append(m)

        in_qty = out_qty = transfer_qty = 0.0
        movements = []
        for (vtype, vno), rows_ in by_voucher.items():
            pos = sum(flt(m.actual_qty) for m in rows_ if flt(m.actual_qty) > 0)
            neg = sum(abs(flt(m.actual_qty)) for m in rows_ if flt(m.actual_qty) < 0)
            transfer = min(pos, neg)
            in_qty += pos - transfer
            out_qty += neg - transfer
            transfer_qty += transfer
            party = _party_for_voucher(vtype, vno)
            first = rows_[0]
            if transfer > 0:
                movements.append({
                    "voucher_type": vtype, "voucher_no": vno,
                    "qty": round(transfer, 3), "uom": first.stock_uom,
                    "date": str(first.posting_date),
                    "warehouse": first.warehouse, "party": party,
                    "is_transfer": True,
                })
                net = round((pos - neg), 3)
                if abs(net) > 1e-6:
                    movements.append({
                        "voucher_type": vtype, "voucher_no": vno,
                        "qty": net, "uom": first.stock_uom,
                        "date": str(first.posting_date),
                        "warehouse": first.warehouse, "party": party,
                        "is_transfer": False,
                    })
            else:
                movements.append({
                    "voucher_type": vtype, "voucher_no": vno,
                    "qty": round(pos - neg, 3), "uom": first.stock_uom,
                    "date": str(first.posting_date),
                    "warehouse": first.warehouse, "party": party,
                    "is_transfer": False,
                })

        movements.sort(key=lambda m: m["date"])
        balance = round(in_qty - out_qty, 2)

        # Loss badge: this stage's In vs the previous stage's Out (BOM-aware
        # via check_stage_loss's tolerance would need output_item context;
        # here we use the simple settings tolerance for a quick visual cue).
        loss_pct = None
        if prev_out_qty and prev_out_qty > 0:
            loss_pct = round((prev_out_qty - in_qty) / prev_out_qty * 100, 2)
        prev_out_qty = out_qty if out_qty else in_qty

        nodes.append({
            "batch": b.name,
            "item": b.item,
            "stage": b.process_stage,
            "in_qty": round(in_qty, 2),
            "out_qty": round(out_qty, 2),
            "transfer_qty": round(transfer_qty, 2),
            "balance": balance,
            "loss_pct": loss_pct,
            "loss_over_tolerance": (loss_pct is not None and tol > 0
                                    and loss_pct > tol),
            "movements": movements,
        })

    return {"lot": lot, "batches": nodes}


@frappe.whitelist()
def get_trace_tree(root_lot):
    """Alias kept for older page JS."""
    return get_lot_tree(root_lot)