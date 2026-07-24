# -*- coding: utf-8 -*-
# Phase 6 V2 — Resolver (simplified, reads from Lot Naming Rule, not Profile)
#
# Core logic is identical to Phase 6 V1:
#   - PRIMARY yarn opens new lot (serial +1)
#   - SECONDARY yarn reuses oldest open lot waiting for it (FIFO)
#   - Batch naming is hardcoded (no config patterns)
#
# Config reading is MUCH simpler: just read the Lot Naming Rule (Yarns table).

import re
import frappe
from frappe.utils import nowdate


# ---------------------------------------------------------------------------
# Rule and yarn resolution
# ---------------------------------------------------------------------------

def find_naming_rule_for_item(item_code):
    """Find the Lot Naming Rule (and its yarn row) for a greige item.

    Returns (rule_name, yarn_row_dict) or (None, None).
    """
    # Find all rules that list this item in their Yarns table
    rules = frappe.get_all(
        "Lot Naming Rule",
        filters={"active": 1},
        fields=["name"],
    )

    for rule in rules:
        yarns = frappe.get_all(
            "Lot Naming Rule Yarn",
            filters={"parent": rule.name, "yarn_item": item_code},
            fields=["name", "yarn_item", "role", "item_abbr"],
        )
        if yarns:
            return rule.name, yarns[0]

    # Fallback: check legacy yarn_item field (Phase 5 compatibility)
    rule = frappe.db.get_value(
        "Lot Naming Rule", {"yarn_item": item_code, "active": 1}, "name"
    )
    if rule:
        return rule, {"yarn_item": item_code, "role": "Primary", "item_abbr": None}

    return None, None


def get_product_for_rule(rule_name):
    """Return the product (finished good) for a rule."""
    return frappe.db.get_value("Lot Naming Rule", rule_name, "product")


def get_all_yarns_for_rule(rule_name):
    """Return all yarns (Yarns table) for a rule."""
    yarns = frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"parent": rule_name},
        fields=["name", "yarn_item", "role", "item_abbr"],
        order_by="role asc",  # Primary first
    )
    if yarns:
        return yarns
    # Fallback: Phase 5 legacy (single yarn_item field)
    item = frappe.db.get_value("Lot Naming Rule", rule_name, "yarn_item")
    if item:
        return [{"yarn_item": item, "role": "Primary", "item_abbr": None}]
    return []


# ---------------------------------------------------------------------------
# Core decision logic (identical to Phase 6 V1)
# ---------------------------------------------------------------------------

def resolve_open_lot(item_code, po_root_lot=None):
    """Decide which Root Lot an incoming greige receipt belongs to.

    Returns {"action": "create"|"reuse"|"hold", "root_lot": name-or-None,
             "rule": rule_name, "yarn_row": dict, "role": "Primary"|"Secondary",
             "ambiguous": bool, "candidates": [names]}
    """
    rule, yarn_row = find_naming_rule_for_item(item_code)
    if not rule:
        return {
            "action": None, "root_lot": None, "rule": None, "yarn_row": None,
            "role": None, "ambiguous": False, "candidates": [],
        }

    product = get_product_for_rule(rule)
    role = yarn_row.get("role", "Primary")

    if role == "Primary":
        return {
            "action": "create", "root_lot": None, "rule": rule, "yarn_row": yarn_row,
            "role": role, "ambiguous": False, "candidates": [],
        }

    # Secondary yarn: find waiting lots
    if po_root_lot and _lot_is_waiting_for(po_root_lot, item_code):
        return {
            "action": "reuse", "root_lot": po_root_lot, "rule": rule,
            "yarn_row": yarn_row, "role": role, "ambiguous": False,
            "candidates": [po_root_lot],
        }

    candidates = _open_lots_waiting_for(product, item_code)
    if len(candidates) == 1:
        return {
            "action": "reuse", "root_lot": candidates[0], "rule": rule,
            "yarn_row": yarn_row, "role": role, "ambiguous": False,
            "candidates": candidates,
        }

    if len(candidates) == 0:
        return {
            "action": "hold", "root_lot": None, "rule": rule, "yarn_row": yarn_row,
            "role": role, "ambiguous": False, "candidates": [],
        }

    # Multiple waiting lots: FIFO
    ordered = _order_lots_fifo(candidates)
    oldest = ordered[0]
    same_day_tie = _same_day_tie(ordered)

    return {
        "action": "reuse", "root_lot": oldest, "rule": rule, "yarn_row": yarn_row,
        "role": role, "ambiguous": bool(same_day_tie),
        "candidates": ordered,
    }


def _lot_is_waiting_for(root_lot, item_code):
    rl = frappe.db.get_value(
        "Root Lot", root_lot, ["intake_complete", "product"], as_dict=True
    )
    if not rl or rl.intake_complete:
        return False
    has = frappe.db.exists("Lot Receipt", {"parent": root_lot, "yarn_item": item_code})
    return not has


def _open_lots_waiting_for(product, item_code):
    rule = frappe.db.get_value("Lot Naming Rule", {"product": product, "active": 1}, "name")
    if not rule:
        return []
    open_lots = frappe.get_all(
        "Root Lot",
        filters={"naming_rule": rule, "intake_complete": 0},
        fields=["name"],
        order_by="creation asc",
    )
    waiting = []
    for lot in open_lots:
        has = frappe.db.exists("Lot Receipt", {"parent": lot.name, "yarn_item": item_code})
        if not has:
            waiting.append(lot.name)
    return waiting


def _order_lots_fifo(lot_names):
    rows = frappe.get_all(
        "Root Lot",
        filters={"name": ["in", lot_names]},
        fields=["name", "creation"],
        order_by="creation asc",
    )
    return [r.name for r in rows]


def _same_day_tie(ordered_lot_names):
    if len(ordered_lot_names) < 2:
        return False
    rows = frappe.get_all(
        "Root Lot",
        filters={"name": ["in", ordered_lot_names[:2]]},
        fields=["name", "creation"],
    )
    days = {str(r.creation)[:10] for r in rows}
    return len(days) == 1


# ---------------------------------------------------------------------------
# Hardcoded batch naming (no config patterns, no tokens)
# ---------------------------------------------------------------------------

def render_batch_name(lot_code, stage, abbr=None, color_abbr=None):
    """Build batch name from lot code + stage + abbr + color.

    Hardcoded patterns (no config):
      NT: {lot}-{abbr}-NT
      DY: {lot}-{abbr}-{color}-DY
      WV: {lot}-WV
      CT: {lot}-CT
    """
    if not lot_code:
        return None

    if stage == "NT":
        return f"{lot_code}-{abbr}-NT" if abbr else f"{lot_code}-NT"
    elif stage == "DY":
        if abbr and color_abbr:
            return f"{lot_code}-{abbr}-{color_abbr}-DY"
        elif abbr:
            return f"{lot_code}-{abbr}-DY"
        else:
            return f"{lot_code}-DY"
    elif stage == "WV":
        return f"{lot_code}-WV"
    elif stage == "CT":
        return f"{lot_code}-CT"
    else:
        return f"{lot_code}-{stage}"


# ---------------------------------------------------------------------------
# Item helpers
# ---------------------------------------------------------------------------

def extract_base_yarn_item(item_code):
    """Strip -DYE-, -DY-, -CT suffixes to get greige item code."""
    if not item_code:
        return None
    m = re.match(
        r"(.*?-(?:CN|RM|WL|SLK|YRN|POL)?)(?:-DYE|-DY|-CT)?(?:-[A-Z]{2,})?$",
        item_code,
    )
    if m:
        return m.group(1).rstrip("-")
    return item_code


def color_abbr_for_item(item_code):
    """Extract color abbreviation from a dyed item code."""
    if not item_code:
        return None
    # Try item variant attribute first
    try:
        attr = frappe.db.get_value(
            "Item Variant Attribute",
            {"parent": item_code, "attribute": ["like", "%Colour%"]},
            "attribute_value",
        )
        if not attr:
            attr = frappe.db.get_value(
                "Item Variant Attribute",
                {"parent": item_code, "attribute": ["like", "%Color%"]},
                "attribute_value",
            )
        if attr:
            abbr = frappe.db.get_value("Item Attribute Value", {"attribute_value": attr}, "abbr")
            if abbr:
                return abbr.upper()
    except Exception:
        pass

    # Trailing segment after -DYE- or -DY-
    m = re.search(r"-(?:DYE|DY)-([A-Z0-9]{2,})$", item_code.upper())
    if m:
        return m.group(1)

    # Fallback
    return None
