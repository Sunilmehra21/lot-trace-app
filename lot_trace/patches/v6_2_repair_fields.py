# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Repair patch.
#
# Fixes, in order:
#   Bug 4: duplicate "lot_route" field on Lot Naming Rule (one came from the
#          site's existing Custom Field, one from my V2 doctype JSON) and the
#          leftover Legacy (Phase 5) section fields.
#   Bug 5: docs named after the product (autoname field:product) — renames
#          existing rules to the LNR-#### series so the product field stays
#          visible after save (title_field shows it in the header instead).
#   Missing: "naming_rule" link field on Root Lot (lot_factory writes it, but
#          no patch ever created it — silent data loss until now).
#
# Idempotent: safe to run more than once.

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    _remove_duplicate_and_legacy_fields()
    _ensure_root_lot_naming_rule_field()
    _rename_rules_off_product_autoname()
    frappe.clear_cache(doctype="Lot Naming Rule")
    frappe.clear_cache(doctype="Root Lot")
    print("✓ Phase 6.2 repair complete")


# ---------------------------------------------------------------------------
# Bug 4 — duplicate lot_route + legacy fields
# ---------------------------------------------------------------------------

def _remove_duplicate_and_legacy_fields():
    # The V2 doctype JSON no longer defines lot_route / legacy fields, so any
    # remaining copies live as Custom Fields. Delete them.
    stale = ["lot_route", "yarn_item", "legacy_note", "section_legacy"]
    removed = 0
    for fieldname in stale:
        names = frappe.get_all(
            "Custom Field",
            filters={"dt": "Lot Naming Rule", "fieldname": fieldname},
            pluck="name",
        )
        for n in names:
            frappe.delete_doc("Custom Field", n, ignore_permissions=True, force=True)
            removed += 1

    # Also drop Property Setters that may pin the old layout.
    ps = frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Lot Naming Rule",
                 "field_name": ["in", stale]},
        pluck="name",
    )
    for n in ps:
        frappe.delete_doc("Property Setter", n, ignore_permissions=True, force=True)

    if removed:
        print(f"  ✓ removed {removed} duplicate/legacy field(s) from Lot Naming Rule")
    else:
        print("  ✓ no duplicate/legacy fields found (already clean)")


# ---------------------------------------------------------------------------
# Missing Root Lot.naming_rule link
# ---------------------------------------------------------------------------

def _ensure_root_lot_naming_rule_field():
    meta = frappe.get_meta("Root Lot")
    if meta.get_field("naming_rule"):
        print("  ✓ Root Lot.naming_rule already exists")
        return
    create_custom_fields({
        "Root Lot": [{
            "fieldname": "naming_rule",
            "label": "Lot Naming Rule",
            "fieldtype": "Link",
            "options": "Lot Naming Rule",
            "insert_after": "product",
            "read_only": 1,
        }],
    }, ignore_validate=True)
    print("  ✓ added Root Lot.naming_rule link field")

    # Backfill: lots created while the field was missing lost the value on
    # save. Recover it from the product.
    lots = frappe.get_all(
        "Root Lot", filters={"naming_rule": ["in", ["", None]]},
        fields=["name", "product"],
    )
    fixed = 0
    for lot in lots:
        if not lot.product:
            continue
        rule = frappe.db.get_value(
            "Lot Naming Rule", {"product": lot.product}, "name"
        )
        if rule:
            frappe.db.set_value("Root Lot", lot.name, "naming_rule", rule,
                                update_modified=False)
            fixed += 1
    if fixed:
        print(f"  ✓ backfilled naming_rule on {fixed} existing Root Lot(s)")


# ---------------------------------------------------------------------------
# Bug 5 — rename rules off the product-based autoname
# ---------------------------------------------------------------------------

def _rename_rules_off_product_autoname():
    """Old autoname was field:product, so doc name == product code and Frappe
    hid the product field after save. New autoname is LNR-#### with
    title_field=product. Rename existing docs to the new series."""
    rules = frappe.get_all("Lot Naming Rule", fields=["name", "product"])
    counter = 0
    for r in rules:
        if r.name.startswith("LNR-"):
            continue
        counter += 1
        new_name = _next_lnr_name()
        frappe.rename_doc("Lot Naming Rule", r.name, new_name,
                          ignore_permissions=True, force=True)
        print(f"  ✓ renamed rule '{r.name}' -> {new_name} (product stays visible)")
    if not counter:
        print("  ✓ all rules already on LNR-#### naming")


def _next_lnr_name():
    existing = frappe.get_all(
        "Lot Naming Rule",
        filters={"name": ["like", "LNR-%"]},
        pluck="name",
    )
    max_n = 0
    for n in existing:
        try:
            max_n = max(max_n, int(n.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return f"LNR-{max_n + 1:04d}"
