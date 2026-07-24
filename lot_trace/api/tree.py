# Trace tree API — Phase 5 fixes:
# 1. Multi-color DY batches are SIBLING nodes (same depth), not nested.
#    Batches of the same stage are grouped; the group's In/Out is the sum
#    of all its batches.  Loss is computed group-to-group (NT-total vs
#    DY-total), not batch-to-first-batch.
# 2. Side panel Stage Progress sums all batches of a stage together.

import frappe
from frappe import _
from frappe.utils import flt

PARTY_FIELD = {
    "Purchase Receipt": "supplier",
    "Purchase Invoice": "supplier",
    "Subcontracting Receipt": "supplier",
    "Stock Entry": "supplier",
    "Delivery Note": "customer",
    "Sales Invoice": "customer",
}


@frappe.whitelist()
def get_trace_tree(root_lot):
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

    # planned route for progress bar
    from lot_trace.events.common import get_route_stages
    planned = get_route_stages(root_lot) or frappe.get_all(
        "Lot Process Stage", filters={"active": 1},
        order_by="sequence asc", pluck="name")
    lot["planned_stages"] = planned

    # all batches of this lot ordered by stage sequence
    batches = frappe.db.sql("""
        SELECT b.name AS batch, b.item, b.process_stage,
               s.stage_name, s.sequence, s.expected_loss_pct
        FROM `tabBatch` b
        LEFT JOIN `tabLot Process Stage` s ON s.name = b.process_stage
        WHERE b.root_lot = %s
        ORDER BY COALESCE(s.sequence, 99), b.name
    """, root_lot, as_dict=True)

    # ── Build per-BATCH data (movements, in/out, transfers) ──────────
    party_cache = {}
    batch_data = []
    for b in batches:
        movements = frappe.db.sql("""
            SELECT sle.posting_date, sle.voucher_type, sle.voucher_no,
                   sle.actual_qty, sle.warehouse, sle.stock_uom
            FROM `tabStock Ledger Entry` sle
            WHERE sle.batch_no = %s AND sle.is_cancelled = 0
            ORDER BY sle.posting_date, sle.posting_time, sle.name
        """, b.batch, as_dict=True)

        by_voucher = {}
        for m in movements:
            by_voucher.setdefault((m.voucher_type, m.voucher_no), []).append(m)

        in_qty = out_qty = consumed_qty = 0.0
        transfer_vouchers = set()
        for key, rows in by_voucher.items():
            pos = sum(flt(m.actual_qty) for m in rows if flt(m.actual_qty) > 0)
            neg = sum(abs(flt(m.actual_qty)) for m in rows if flt(m.actual_qty) < 0)
            transfer = min(pos, neg)
            if transfer > 0:
                transfer_vouchers.add(key)
            in_qty += pos - transfer
            out_qty += neg - transfer
            if key[0] == "Subcontracting Receipt":
                consumed_qty += neg

        uom = movements[0].stock_uom if movements else ""

        mv_out = []
        for m in movements:
            key = (m.voucher_type, m.voucher_no)
            if key not in party_cache:
                field = PARTY_FIELD.get(m.voucher_type)
                try:
                    party = frappe.db.get_value(
                        m.voucher_type, m.voucher_no, field) if field else None
                except Exception:
                    party = None
                party_cache[key] = party or ""
            mv_out.append({
                "date": str(m.posting_date),
                "voucher_type": m.voucher_type,
                "voucher_no": m.voucher_no,
                "qty": flt(m.actual_qty),
                "warehouse": m.warehouse,
                "party": party_cache[key],
                "is_transfer": key in transfer_vouchers,
            })

        batch_data.append({
            "batch": b.batch,
            "stage": b.process_stage,
            "stage_name": b.stage_name or b.process_stage,
            "sequence": b.sequence or 0,
            "expected_loss_pct": flt(b.expected_loss_pct),
            "item": b.item,
            "item_name": frappe.db.get_value("Item", b.item, "item_name") or b.item,
            "uom": uom,
            "in_qty": round(in_qty, 2),
            "out_qty": round(out_qty, 2),
            "consumed_qty": round(consumed_qty, 2),
            "balance": round(in_qty - out_qty, 2),
            "movements": mv_out,
        })

    # ── Group batches by stage → stage-level nodes ───────────────────
    # Same stage = SIBLINGS (e.g. BK-DY and WH-DY are siblings at DY level).
    # The node returned to the frontend represents the STAGE with aggregated
    # totals; individual batch details are in "sub_batches".
    from collections import OrderedDict
    stage_groups = OrderedDict()
    for bd in batch_data:
        s = bd["stage"]
        if s not in stage_groups:
            stage_groups[s] = {
                "stage": s,
                "stage_name": bd["stage_name"],
                "sequence": bd["sequence"],
                "expected_loss_pct": bd["expected_loss_pct"],
                "uom": bd["uom"],
                "in_qty": 0.0, "out_qty": 0.0, "consumed_qty": 0.0,
                "sub_batches": [],
                "all_movements": [],
            }
        g = stage_groups[s]
        g["in_qty"] += bd["in_qty"]
        g["out_qty"] += bd["out_qty"]
        g["consumed_qty"] += bd["consumed_qty"]
        g["sub_batches"].append(bd)
        g["all_movements"].extend(bd["movements"])

    # Compute loss per STAGE (previous stage's consumed_qty vs this stage's in_qty)
    from lot_trace.events.common import expected_input_per_unit
    nodes = []
    prev_group = None
    for stage_code, g in stage_groups.items():
        in_qty = round(g["in_qty"], 2)
        out_qty = round(g["out_qty"], 2)
        consumed_qty = round(g["consumed_qty"], 2)

        loss_qty = loss_pct = None
        loss_over = False
        if prev_group and flt(prev_group["consumed_qty"]) > 0 and in_qty > 0:
            prev_consumed = round(flt(prev_group["consumed_qty"]), 2)
            actual_loss = prev_consumed - in_qty
            loss_qty = round(actual_loss, 2)
            loss_pct = round(actual_loss / prev_consumed * 100, 2)
            # Use BOM of ANY item in this stage group
            for sb in g["sub_batches"]:
                per_unit = expected_input_per_unit(sb["item"])
                if per_unit > 0:
                    loss_over = prev_consumed > in_qty * per_unit + 0.1
                    break
            else:
                if flt(g["expected_loss_pct"]) > 0:
                    loss_over = loss_pct > flt(g["expected_loss_pct"]) + 0.01

        nodes.append({
            # For single-batch stages, batch = the one batch name (tree nav)
            # For multi-batch stages, batch = the first batch
            "batch": g["sub_batches"][0]["batch"],
            "stage": stage_code,
            "stage_name": g["stage_name"],
            "sequence": g["sequence"],
            "item": g["sub_batches"][0]["item"],
            "item_name": g["sub_batches"][0]["item_name"],
            "uom": g["uom"],
            "in_qty": in_qty,
            "out_qty": out_qty,
            "consumed_qty": consumed_qty,
            "balance": round(in_qty - out_qty, 2),
            "loss_qty": loss_qty,
            "loss_pct": loss_pct,
            "loss_over": loss_over,
            # multi-batch stages list their sub-batches for the frontend
            "sub_batches": g["sub_batches"] if len(g["sub_batches"]) > 1 else [],
            "movements": g["all_movements"],
        })
        prev_group = g

    # CASE 2 — multi-lot weaving merges
    merged_from = frappe.db.sql("""
        SELECT lcd.root_lot, SUM(lcd.qty_kg) AS qty_kg
        FROM `tabLot Consumption Detail` lcd
        JOIN `tabPurchase Receipt` pr ON pr.name = lcd.parent
            AND lcd.parenttype = 'Purchase Receipt'
        JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
        WHERE pri.root_lot = %s AND pr.docstatus = 1 AND lcd.root_lot != %s
        GROUP BY lcd.root_lot
    """, (root_lot, root_lot), as_dict=True)
    for n in nodes:
        if n["stage"] == "WV" and merged_from:
            n["merged_from"] = [
                {"root_lot": m.root_lot, "qty_kg": flt(m.qty_kg)}
                for m in merged_from]

    merged_into = frappe.db.sql("""
        SELECT pri.root_lot AS primary_lot, SUM(lcd.qty_kg) AS qty_kg
        FROM `tabLot Consumption Detail` lcd
        JOIN `tabPurchase Receipt` pr ON pr.name = lcd.parent
            AND lcd.parenttype = 'Purchase Receipt'
        JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
        WHERE lcd.root_lot = %s AND pr.docstatus = 1 AND pri.root_lot != %s
        GROUP BY pri.root_lot
    """, (root_lot, root_lot), as_dict=True)
    lot["merged_into"] = [
        {"root_lot": m.primary_lot, "qty_kg": flt(m.qty_kg)}
        for m in merged_into]

    return {"lot": lot, "nodes": nodes}
