# -*- coding: utf-8 -*-
# Phase 6 — Lot Trace Tree data API.
# Builds the primary/secondary sibling tree for one Root Lot by READING stock
# ledger entries and batches. Writes nothing.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver


@frappe.whitelist()
def get_lot_tree(root_lot):
    """Return a nested structure describing the whole production lot.

    {
      "lot": "MV/BG/0726/01", "product": ..., "status": ...,
      "chains": [   # one per yarn (primary first)
        {"role": "Primary", "abbr": "A", "yarn_item": ...,
         "stages": {"NT": {...}, "DY": {"total": .., "batches": [..]}}},
        ...
      ],
      "shared": {"WV": {...}, "CT": {...}}
    }
    """
    rl = frappe.get_doc("Root Lot", root_lot)
    profile = rl.profile
    lot_code = rl.lot_code or rl.name

    trace_items = frappe.get_all(
        "Lot Trace Item", filters={"parent": profile},
        fields=["yarn_item", "item_abbr", "role", "bom_kg_per_pc"],
        order_by="role asc",  # 'Primary' < 'Secondary' alphabetically
    )
    # Ensure primary first explicitly.
    trace_items.sort(key=lambda r: 0 if r.role == "Primary" else 1)

    batches = frappe.get_all(
        "Batch",
        filters={"custom_root_lot": root_lot},
        fields=["name", "item", "custom_stage"],
    )

    chains = []
    for ti in trace_items:
        chain = {
            "role": ti.role, "abbr": ti.item_abbr, "yarn_item": ti.yarn_item,
            "stages": {},
        }
        for stage in ("NT", "DY"):
            stage_batches = [
                b for b in batches
                if b.custom_stage == stage
                and resolver.extract_base_yarn_item(b.item) == ti.yarn_item
            ]
            if not stage_batches:
                continue
            chain["stages"][stage] = _stage_node(stage_batches)
        chain["loss_pct"] = _chain_loss(chain)
        chains.append(chain)

    shared = {}
    for stage in ("WV", "CT"):
        stage_batches = [b for b in batches if b.custom_stage == stage]
        if stage_batches:
            shared[stage] = _stage_node(stage_batches)

    return {
        "lot": lot_code,
        "product": rl.product,
        "status": rl.get("status"),
        "chains": chains,
        "shared": shared,
    }


def _stage_node(stage_batches):
    """Aggregate in/out/balance across sibling batches of one stage."""
    total_in = total_out = total_bal = 0.0
    rows = []
    for b in stage_batches:
        agg = _batch_movement(b.name)
        total_in += agg["in_qty"]
        total_out += agg["out_qty"]
        total_bal += agg["balance"]
        rows.append({"batch": b.name, "item": b.item, **agg})
    return {
        "in_qty": total_in, "out_qty": total_out, "balance": total_bal,
        "batches": rows,
    }


def _batch_movement(batch_no):
    """Net in/out/balance for a batch across all warehouses (READ SLE)."""
    rows = frappe.db.sql(
        """
        SELECT
            COALESCE(SUM(CASE WHEN actual_qty > 0 THEN actual_qty ELSE 0 END), 0) AS in_qty,
            COALESCE(SUM(CASE WHEN actual_qty < 0 THEN -actual_qty ELSE 0 END), 0) AS out_qty,
            COALESCE(SUM(actual_qty), 0) AS balance
        FROM `tabStock Ledger Entry`
        WHERE batch_no = %s AND is_cancelled = 0
        """,
        (batch_no,), as_dict=True,
    )
    r = rows[0] if rows else {"in_qty": 0, "out_qty": 0, "balance": 0}
    return {"in_qty": flt(r.in_qty), "out_qty": flt(r.out_qty), "balance": flt(r.balance)}


def _chain_loss(chain):
    """Loss % from NT consumed to DY produced for one yarn chain."""
    nt = chain["stages"].get("NT")
    dy = chain["stages"].get("DY")
    if not nt or not dy:
        return None
    nt_consumed = nt["out_qty"]
    dy_in = dy["in_qty"]
    if nt_consumed <= 0:
        return None
    return round((nt_consumed - dy_in) / nt_consumed * 100.0, 2)
