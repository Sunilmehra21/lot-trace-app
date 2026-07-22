# -*- coding: utf-8 -*-
# Rule / lot resolution (v6 multi-yarn design):
#   Primary yarn receipt  -> NEW lot
#   Secondary yarn receipt-> FIFO reuse of the oldest OPEN lot that has not
#                            yet received this yarn
# Honors Item.lot_trace_enabled and Lot Naming Rule.active.

import frappe


def find_naming_rule_for_item(item_code):
    """(rule doc dict, yarn child row) when item_code is a configured yarn
    in an ACTIVE Lot Naming Rule, else (None, None)."""
    if not item_code:
        return None, None

    item_enabled = frappe.db.get_value("Item", item_code, "lot_trace_enabled")
    if item_enabled is not None and not int(item_enabled or 0):
        return None, None

    rows = frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"yarn_item": item_code, "parenttype": "Lot Naming Rule"},
        fields=["parent", "yarn_item", "role", "item_abbr"])
    for r in rows:
        rule = frappe.db.get_value(
            "Lot Naming Rule", r.parent,
            ["name", "product", "lot_code_prefix", "route", "active"],
            as_dict=True)
        if rule and rule.active:
            return rule, r
    return None, None


def resolve_open_lot(item_code):
    """Decision for a yarn receipt:
    {'action': 'new'|'reuse'|'blocked'|'none', ...}"""
    rule, yarn_row = find_naming_rule_for_item(item_code)
    if not rule:
        return {"action": "none"}

    if (yarn_row.role or "Primary") == "Primary":
        return {"action": "new", "rule": rule, "yarn_row": yarn_row}

    lots = frappe.get_all(
        "Root Lot",
        filters={"naming_rule": rule.name, "status": ["in", ["Open", "In Process"]],
                 "intake_complete": 0},
        pluck="name", order_by="creation asc")
    for lot in lots:
        already = frappe.get_all(
            "Lot Receipt",
            filters={"parent": lot, "parenttype": "Root Lot",
                     "yarn_item": item_code},
            limit=1)
        if not already:
            return {"action": "reuse", "root_lot": lot,
                    "rule": rule, "yarn_row": yarn_row}
    return {"action": "blocked", "rule": rule, "yarn_row": yarn_row}
