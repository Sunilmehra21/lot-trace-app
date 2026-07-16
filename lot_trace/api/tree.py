# Trace tree API: builds the full stage-chain of a Root Lot from native
# Batch records + Stock Ledger Entries. Powers the Lot Trace Tree page.

import frappe
from frappe import _
from frappe.utils import flt

# voucher type -> party field on that doctype
PARTY_FIELD = {
    "Purchase Receipt": "supplier",
    "Purchase Invoice": "supplier",
    "Subcontracting Receipt": "supplier",
    "Stock Entry": "supplier",          # set on Send to Subcontractor entries
    "Delivery Note": "customer",
    "Sales Invoice": "customer",
}


@frappe.whitelist()
def get_trace_tree(root_lot):
    """Return the Root Lot header + ordered stage nodes with movements.

    Nodes are returned in FORWARD stage order (NT -> FG); the page can
    render them forward or backward.

    Internal warehouse transfers (same voucher writes both + and - SLE
    rows for the SAME batch, e.g. company WH -> job worker WH) are netted
    out of In/Out totals and flagged is_transfer on the movement.
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

    party_cache = {}
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

        # group by voucher: a voucher with both + and - rows for this batch
        # is an internal transfer for the overlapping qty
        by_voucher = {}
        for m in movements:
            by_voucher.setdefault((m.voucher_type, m.voucher_no), []).append(m)

        in_qty = out_qty = consumed_qty = 0.0
        transfer_vouchers = set()
        for key, rows in by_voucher.items():
            pos = sum(flt(m.actual_qty) for m in rows if flt(m.actual_qty) > 0)
            neg = sum(abs(flt(m.actual_qty)) for m in rows if flt(m.actual_qty) < 0)
            transfer = min(pos, neg)  # internally moved portion (net zero)
            if transfer > 0:
                transfer_vouchers.add(key)
            in_qty += pos - transfer
            out_qty += neg - transfer
            if key[0] == "Subcontracting Receipt":
                consumed_qty += neg  # consumed as raw material at a processor

        uom = movements[0].stock_uom if movements else ""

        mv_out = []
        for m in movements:
            key = (m.voucher_type, m.voucher_no)
            if key not in party_cache:
                field = PARTY_FIELD.get(m.voucher_type)
                party = None
                if field:
                    try:
                        party = frappe.db.get_value(m.voucher_type, m.voucher_no, field)
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
            "consumed_qty": round(consumed_qty, 2),
            "balance": round(in_qty - out_qty, 2),
            "movements": mv_out,
        })

    # process loss per stage: previous stage's qty consumed at the processor
    # (via Subcontracting Receipt) vs this stage's qty received back.
    # ACTUAL loss = consumed - received; expected consumption from the output
    # item's BOM (e.g. 1.05 kg NT per kg DY). Falls back to stage % tolerance.
    from lot_trace.events.common import expected_input_per_unit
    prev = None
    for n in nodes:
        n["loss_pct"] = None
        n["loss_qty"] = None
        n["loss_over"] = False
        consumed = flt(prev.get("consumed_qty")) if prev else 0
        received = flt(n["in_qty"])
        if prev and consumed > 0 and received > 0:
            actual_loss = consumed - received
            n["loss_qty"] = round(actual_loss, 2)
            n["loss_pct"] = round(actual_loss / consumed * 100, 2)
            per_unit = expected_input_per_unit(n["item"])
            if per_unit > 0:
                # BOM-based: over-loss when consumed exceeds BOM allowance
                n["loss_over"] = consumed > received * per_unit + 0.1
                n["expected_loss_qty"] = round(received * per_unit - received, 2)
            elif flt(n["expected_loss_pct"]) > 0:
                n["loss_over"] = n["loss_pct"] > flt(n["expected_loss_pct"]) + 0.01
        prev = n

    # CASE 2 — multi-lot weaving merges
    # secondary lots whose dyed yarn was consumed into THIS lot's weaving:
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

    # was THIS lot's dyed yarn consumed into another primary lot?
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
