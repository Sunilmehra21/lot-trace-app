# -*- coding: utf-8 -*-
# Phase 6 — Migrate legacy Lot Naming Rules into Lot Trace Profiles.
#
# Legacy model: one Lot Naming Rule per (product, yarn_item).
# New model:    one Lot Trace Profile per product, with all yarns as Trace Items.
#
# Conversion:
#   * Group legacy rules by product.
#   * The FIRST rule's yarn item becomes PRIMARY (abbr 'A').
#   * Remaining yarns become SECONDARY (abbr 'B', 'C', ...).
#   * Seed default batch naming rules (NT/DY/WV/CT).
# Legacy rules are left intact (read-only) so nothing breaks mid-migration.

import frappe

_ABBRS = list("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

_DEFAULT_BATCH_RULES = [
    {"stage": "NT", "pattern": "{LOT}-{ABBR}-NT", "example": "01-A-NT"},
    {"stage": "DY", "pattern": "{LOT}-{ABBR}-{COLOR}-DY", "example": "01-A-BK-DY"},
    {"stage": "WV", "pattern": "{LOT}-WV", "example": "01-WV"},
    {"stage": "CT", "pattern": "{LOT}-CT", "example": "01-CT"},
]


def execute():
    if not frappe.db.exists("DocType", "Lot Naming Rule"):
        print("No legacy Lot Naming Rule doctype; skipping conversion.")
        return

    legacy = frappe.get_all(
        "Lot Naming Rule",
        fields=["name", "product", "yarn_item", "creation"],
        order_by="creation asc",
    )
    if not legacy:
        print("No legacy Lot Naming Rules to convert.")
        return

    by_product = {}
    lot_pattern_by_product = {}
    for r in legacy:
        by_product.setdefault(r.product, []).append(r)
        # Try to carry over a pattern if the legacy rule had one.
        pat = frappe.db.get_value("Lot Naming Rule", r.name, "lot_code_pattern") \
            if _lnr_has_field("lot_code_pattern") else None
        if pat and r.product not in lot_pattern_by_product:
            lot_pattern_by_product[r.product] = pat

    created = 0
    for product, rules in by_product.items():
        if frappe.db.exists("Lot Trace Profile", {"product": product}):
            continue  # already migrated

        profile = frappe.get_doc({
            "doctype": "Lot Trace Profile",
            "product": product,
            "active": 1,
            "lot_code_pattern": lot_pattern_by_product.get(product, "MV/BG/{MMYY}/{##}"),
            "route": "NT → DY → WV → CT",
            "weaving_tolerance_pct": 2,
        })

        seen_items = []
        for idx, r in enumerate(rules):
            if r.yarn_item in seen_items:
                continue
            seen_items.append(r.yarn_item)
            profile.append("trace_items", {
                "yarn_item": r.yarn_item,
                "role": "Primary" if idx == 0 else "Secondary",
                "item_abbr": _ABBRS[len(seen_items) - 1],
                "bom_kg_per_pc": 0,
            })

        for br in _DEFAULT_BATCH_RULES:
            profile.append("batch_naming_rules", dict(br))

        profile.insert(ignore_permissions=True)
        created += 1
        print(f"  ✓ {product}: profile created with {len(seen_items)} yarn(s), "
              f"primary = {rules[0].yarn_item}")

    frappe.db.commit()
    print(f"✓ Phase 6 migration: {created} Lot Trace Profile(s) created. "
          f"Legacy Lot Naming Rules kept read-only.")


def _lnr_has_field(fieldname):
    try:
        return bool(frappe.get_meta("Lot Naming Rule").get_field(fieldname))
    except Exception:
        return False
