# -*- coding: utf-8 -*-
# V7 — Rule / lot resolution. Single source of truth for naming decisions.

import frappe

# Stage codes used by batch naming. Extra stages (ST/EM/FN/PK) exist only in
# the flow chart display; batches are created for these four.
STAGES = ["NT", "DY", "WV", "CT"]

DEFAULT_STAGE_LABELS = [
    ("NT", "Natural/Greige Yarn"),
    ("DY", "Yarn Dyeing"),
    ("WV", "Weaving"),
    ("CT", "Cutting"),
    ("ST", "Stitching"),
    ("EM", "Embroidery"),
    ("FN", "Finishing"),
    ("PK", "Packing"),
]


def find_naming_rule_for_item(item_code):
    """Return (rule dict, yarn child row dict) if item_code is a configured
    greige yarn in an ACTIVE Lot Naming Rule, else (None, None)."""
    rows = frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"yarn_item": item_code, "parenttype": "Lot Naming Rule"},
        fields=["parent", "yarn_item", "role", "item_abbr"],
    )
    for r in rows:
        rule = frappe.db.get_value(
            "Lot Naming Rule", r.parent,
            ["name", "product", "lot_code_prefix", "active"], as_dict=True)
        if rule and rule.active:
            return rule, r
    return None, None


def resolve_open_lot(item_code):
    """Decide what to do for a yarn receipt.
    Primary  -> always {'action': 'new'} (caller creates a lot).
    Secondary-> FIFO: oldest OPEN lot of the same rule that has not yet
                received this yarn -> {'action': 'reuse'}; else 'blocked'."""
    rule, yarn_row = find_naming_rule_for_item(item_code)
    if not rule:
        return {"action": "none"}

    if (yarn_row.role or "Primary") == "Primary":
        return {"action": "new", "rule": rule, "yarn_row": yarn_row}

    lots = frappe.get_all(
        "Root Lot",
        filters={"naming_rule": rule.name, "status": "Open",
                 "intake_complete": 0},
        pluck="name", order_by="creation asc",
    )
    for lot in lots:
        already = frappe.get_all(
            "Lot Receipt",
            filters={"parent": lot, "yarn_item": item_code}, limit=1)
        if not already:
            return {"action": "reuse", "root_lot": lot,
                    "rule": rule, "yarn_row": yarn_row}
    return {"action": "blocked", "rule": rule, "yarn_row": yarn_row}


def render_batch_name(lot_code, stage, abbr=None, color=None):
    """Hardcoded V2 naming — no user-editable tokens.
    NT: MV/BA/0726/01-A-NT   DY: MV/BA/0726/01-A-BK-DY
    WV: MV/BA/0726/01-WV     CT: MV/BA/0726/01-CT"""
    if stage == "NT":
        return f"{lot_code}-{abbr}-NT"
    if stage == "DY":
        return (f"{lot_code}-{abbr}-{color}-DY" if color
                else f"{lot_code}-{abbr}-DY")
    return f"{lot_code}-{stage}"


def color_abbr_for_item(item_code):
    """Short colour code for DY batch names. Tries the Item's variant
    attribute (Colour/Color), then its abbreviation; falls back to a token
    from the item code; never raises."""
    try:
        attr = frappe.get_all(
            "Item Variant Attribute",
            filters={"parent": item_code,
                     "attribute": ["in", ["Colour", "Color"]]},
            fields=["attribute", "attribute_value"], limit=1)
        if attr:
            val = attr[0].attribute_value
            abbr = frappe.db.get_value(
                "Item Attribute Value",
                {"parent": attr[0].attribute, "attribute_value": val},
                "abbr")
            return (abbr or val or "CL")[:4].upper()
    except Exception:
        pass
    # fallback: last short token of the item code (e.g. ...-BK-DY-CN -> BK)
    for token in reversed((item_code or "").split("-")):
        if 1 < len(token) <= 3 and token.isalpha():
            return token.upper()
    return "CL"


def get_flow_stages():
    """Stage columns for the flow chart. Reads the site's Lot Process Stage
    doctype if usable, else falls back to the default 8-stage sequence."""
    if frappe.db.exists("DocType", "Lot Process Stage"):
        try:
            meta = frappe.get_meta("Lot Process Stage")
            code_f = next((f for f in ("stage_code", "code", "abbr")
                           if meta.get_field(f)), None)
            label_f = next((f for f in ("stage_name", "label", "title")
                            if meta.get_field(f)), None)
            seq_f = next((f for f in ("sequence", "idx", "order")
                          if meta.get_field(f)), None)
            if code_f:
                rows = frappe.get_all(
                    "Lot Process Stage",
                    fields=list({code_f, label_f or code_f}),
                    order_by=f"{seq_f} asc" if seq_f else "creation asc")
                out = [(r.get(code_f), r.get(label_f) or r.get(code_f))
                       for r in rows if r.get(code_f)]
                if out:
                    return out
        except Exception:
            pass
    return DEFAULT_STAGE_LABELS
