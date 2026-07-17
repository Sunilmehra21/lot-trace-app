# Lot Flow Chart API: one row per Root Lot, one column per process stage.
# Powers the /app/lot-flow page (grid board like the mockup).

import frappe
from frappe import _
from frappe.utils import flt

YARN_STAGES = {"NT", "DY"}


@frappe.whitelist()
def get_lot_flow(sales_order=None, product=None, root_lot=None):
    frappe.has_permission("Root Lot", "read", throw=True)

    lot_filters = {}
    if sales_order:
        lot_filters["sales_order"] = sales_order
    if product:
        lot_filters["product"] = product
    if root_lot:
        lot_filters["name"] = root_lot

    lots = frappe.get_all(
        "Root Lot", filters=lot_filters,
        fields=["name", "product", "supplier", "sales_order", "received_qty",
                "uom", "current_stage", "fg_qty", "dispatched_qty", "status",
                "purchase_receipt"],
        order_by="name")

    stages = frappe.get_all(
        "Lot Process Stage", filters={"active": 1},
        fields=["name", "stage_name", "sequence"],
        order_by="sequence asc")

    rows = []
    totals = {"yarn_received": 0, "yarn_in_process": 0, "weaved_pcs": 0,
              "fg_qty": 0, "dispatched": 0, "open_exceptions": 0}

    for lot in lots:
        cells = build_cells(lot.name)
        open_exc = frappe.db.count(
            "Lot Exception", {"root_lot": lot.name, "resolved": 0})

        totals["yarn_received"] += flt(lot.received_qty)
        totals["yarn_in_process"] += sum(
            c["balance"] for s, c in cells.items() if s in YARN_STAGES)
        totals["weaved_pcs"] += cells.get("WV", {}).get("in_qty", 0)
        totals["fg_qty"] += flt(lot.fg_qty)
        totals["dispatched"] += flt(lot.dispatched_qty)
        totals["open_exceptions"] += open_exc

        rows.append({
            "lot": lot.name,
            "product": lot.product,
            "supplier": lot.supplier,
            "purchase_receipt": lot.purchase_receipt,
            "status": lot.status,
            "current_stage": lot.current_stage,
            "open_exceptions": open_exc,
            "cells": cells,
        })

    return {
        "stages": stages,
        "rows": rows,
        "totals": {k: round(v, 2) for k, v in totals.items()},
    }


def build_cells(root_lot):
    """Per-stage cell data for one lot: qty in/out/balance (transfers netted),
    the FULL voucher list (so the page can show all of them, not just the
    first), and DY custody (sold to whom, balance there)."""
    sle = frappe.db.sql("""
        SELECT b.process_stage AS stage, sle.voucher_type, sle.voucher_no,
               sle.actual_qty, sle.stock_uom, sle.posting_date
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE b.root_lot = %s AND sle.is_cancelled = 0
        ORDER BY sle.posting_date, sle.posting_time, sle.name
    """, root_lot, as_dict=True)

    # group by stage, then net internal transfers per voucher
    stages = {}
    for m in sle:
        stages.setdefault(m.stage, []).append(m)

    cells = {}
    for stage, movements in stages.items():
        by_voucher = {}
        for m in movements:
            by_voucher.setdefault((m.voucher_type, m.voucher_no), []).append(m)

        in_qty = out_qty = 0.0
        vouchers = []
        sold_to = {}
        for key, rows_ in by_voucher.items():
            pos = sum(flt(m.actual_qty) for m in rows_ if flt(m.actual_qty) > 0)
            neg = sum(abs(flt(m.actual_qty)) for m in rows_ if flt(m.actual_qty) < 0)
            transfer = min(pos, neg)
            in_qty += pos - transfer
            out_qty += neg - transfer
            if transfer == 0:
                vouchers.append({
                    "voucher_type": key[0],
                    "voucher_no": key[1],
                    "qty": round(pos - neg, 2),
                    "date": str(rows_[0].posting_date),
                })
            # DY custody: sold via DN/SI
            if (stage == "DY" and key[0] in ("Delivery Note", "Sales Invoice")
                    and neg > 0):
                customer = frappe.db.get_value(key[0], key[1], "customer")
                if customer:
                    sold_to[customer] = sold_to.get(customer, 0) + (neg - transfer)

        cells[stage] = {
            "in_qty": round(in_qty, 2),
            "out_qty": round(out_qty, 2),
            "balance": round(in_qty - out_qty, 2),
            "uom": movements[0].stock_uom if movements else "",
            "first_voucher": vouchers[0] if vouchers else None,
            "voucher_count": len(vouchers),
            # full list so the page can render/open every transaction
            "vouchers": vouchers,
            "sold_to": [{"party": p, "qty": round(q, 2)}
                        for p, q in sold_to.items()],
        }
    return cells
