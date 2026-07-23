# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Lot Trace Tree API.
# FIXED: the deployed site had the old module without get_trace_tree.
# This file defines get_trace_tree (whitelisted) and keeps get_lot_tree as an
# alias so any older client script keeps working. Accepts flexible filters.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2


@frappe.whitelist()
def get_trace_tree(root_lot=None, product=None, sales_order=None, **kwargs):
    """Build the primary/secondary sibling tree for one Root Lot.

    Accepts root_lot directly, or resolves the latest lot from product /
    sales order so the report page works with any filter combination.
    """
    root_lot = _resolve_root_lot(root_lot, product, sales_order)
    if not root_lot:
        frappe.throw("Select a Root Lot (or a Product with at least one lot).")

    rl = frappe.get_doc("Root Lot", root_lot)
    lot_code = rl.get("lot_code") or rl.name

    yarns = _yarns_for_lot(rl)
    batches = frappe.get_all(
        "Batch",
        filters={"custom_root_lot": root_lot},
        fields=["name", "item", "custom_stage"],
    )

    chains = []
    for y in yarns:
        chain = {
            "role": y.get("role") or "Primary",
            "abbr": y.get("item_abbr"),
            "yarn_item": y.get("yarn_item"),
            "stages": {},
        }
        for stage in ("NT", "DY"):
            stage_batches = [
                b for b in batches
                if b.custom_stage == stage
                and resolver_v2.extract_base_yarn_item(b.item) == y.get("yarn_item")
            ]
            if stage_batches:
                chain["stages"][stage] = _stage_node(stage_batches)
        chain["loss_pct"] = _chain_loss(chain)
        chains.append(chain)

    # Batches whose base item matches no configured yarn still show up
    # under an "Other" chain instead of silently disappearing.
    known_bases = {y.get("yarn_item") for y in yarns}
    orphans = [
        b for b in batches
        if b.custom_stage in ("NT", "DY")
        and resolver_v2.extract_base_yarn_item(b.item) not in known_bases
    ]
    if orphans:
        chains.append({
            "role": "Other", "abbr": None, "yarn_item": None,
            "stages": {"ALL": _stage_node(orphans)}, "loss_pct": None,
        })

    shared = {}
    for stage in ("WV", "CT"):
        stage_batches = [b for b in batches if b.custom_stage == stage]
        if stage_batches:
            shared[stage] = _stage_node(stage_batches)

    return {
        "lot": lot_code,
        "root_lot": root_lot,
        "product": rl.get("product"),
        "status": rl.get("status"),
        "chains": chains,
        "shared": shared,
    }


# Backward-compatible alias for older client scripts.
@frappe.whitelist()
def get_lot_tree(root_lot=None, **kwargs):
    return get_trace_tree(root_lot=root_lot, **kwargs)


# ---------------------------------------------------------------------------

def _resolve_root_lot(root_lot, product, sales_order):
    if root_lot:
        # The filter may pass the lot_code instead of the docname.
        if frappe.db.exists("Root Lot", root_lot):
            return root_lot
        by_code = frappe.db.get_value("Root Lot", {"lot_code": root_lot}, "name")
        if by_code:
            return by_code
    if product:
        rows = frappe.get_all(
            "Root Lot", filters={"product": product},
            fields=["name"], order_by="creation desc", limit=1,
        )
        if rows:
            return rows[0].name
    if sales_order:
        rl = frappe.db.get_value("Root Lot", {"sales_order": sales_order}, "name")
        if rl:
            return rl
    return None


def _yarns_for_lot(rl_doc):
    """Yarns from the naming rule; falls back to legacy profile, then to
    Lot Receipt rows so old lots created before Phase 6.1 still render."""
    rule = rl_doc.get("naming_rule")
    if rule:
        yarns = resolver_v2.get_all_yarns_for_rule(rule)
        if yarns:
            return yarns

    receipts = rl_doc.get("lot_receipts", []) or []
    if receipts:
        return [
            {"yarn_item": r.yarn_item, "role": "Primary" if i == 0 else "Secondary",
             "item_abbr": r.item_abbr}
            for i, r in enumerate(receipts)
        ]

    # Last resort: derive from the lot's NT batches.
    nt = frappe.get_all(
        "Batch", filters={"custom_root_lot": rl_doc.name, "custom_stage": "NT"},
        fields=["item"],
    )
    return [
        {"yarn_item": b.item, "role": "Primary" if i == 0 else "Secondary",
         "item_abbr": None}
        for i, b in enumerate(nt)
    ]


def _stage_node(stage_batches):
    total_in = total_out = total_bal = 0.0
    rows = []
    for b in stage_batches:
        agg = _batch_movement(b.name)
        total_in += agg["in_qty"]
        total_out += agg["out_qty"]
        total_bal += agg["balance"]
        rows.append({"batch": b.name, "item": b.item, **agg})
    return {"in_qty": total_in, "out_qty": total_out, "balance": total_bal,
            "batches": rows}


def _batch_movement(batch_no):
    rows = frappe.db.sql(
        """SELECT
             COALESCE(SUM(CASE WHEN actual_qty > 0 THEN actual_qty ELSE 0 END), 0) AS in_qty,
             COALESCE(SUM(CASE WHEN actual_qty < 0 THEN -actual_qty ELSE 0 END), 0) AS out_qty,
             COALESCE(SUM(actual_qty), 0) AS balance
           FROM `tabStock Ledger Entry`
           WHERE batch_no = %s AND is_cancelled = 0""",
        (batch_no,), as_dict=True,
    )
    r = rows[0] if rows else {"in_qty": 0, "out_qty": 0, "balance": 0}
    return {"in_qty": flt(r.in_qty), "out_qty": flt(r.out_qty),
            "balance": flt(r.balance)}


def _chain_loss(chain):
    nt = chain["stages"].get("NT")
    dy = chain["stages"].get("DY")
    if not nt or not dy or nt["out_qty"] <= 0:
        return None
    return round((nt["out_qty"] - dy["in_qty"]) / nt["out_qty"] * 100.0, 2)
