# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Repair patch (rev 2).
#
# rev 2 fixes:
#   * frappe.rename_doc() was called with ignore_permissions=... which this
#     Frappe version does not accept -> TypeError, migration failed.
#   * Earlier partial runs renamed docs while autoname was still
#     field:product, which OVERWROTE the product field with the new doc name
#     (rules now show product='LNR-07434' etc.). This rev repairs those.
#
# Idempotent: safe to run repeatedly.

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    _remove_duplicate_and_legacy_fields()
    _ensure_root_lot_naming_rule_field()
    _rename_rules_off_product_autoname()
    _repair_corrupted_products()
    frappe.clear_cache(doctype="Lot Naming Rule")
    frappe.clear_cache(doctype="Root Lot")
    print("✓ Phase 6.2 repair complete")


# ---------------------------------------------------------------------------
# Bug 4 — duplicate lot_route + legacy fields
# ---------------------------------------------------------------------------

def _remove_duplicate_and_legacy_fields():
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

    ps = frappe.get_all(
        "Property Setter",
        filters={"doc_type": "Lot Naming Rule", "field_name": ["in", stale]},
        pluck="name",
    )
    for n in ps:
        frappe.delete_doc("Property Setter", n, ignore_permissions=True, force=True)

    print(f"  ✓ removed {removed} duplicate/legacy field(s)" if removed
          else "  ✓ no duplicate/legacy fields found")


# ---------------------------------------------------------------------------
# Missing Root Lot.naming_rule link
# ---------------------------------------------------------------------------

def _ensure_root_lot_naming_rule_field():
    meta = frappe.get_meta("Root Lot")
    if not meta.get_field("naming_rule"):
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

    lots = frappe.get_all(
        "Root Lot", filters={"naming_rule": ["in", ["", None]]},
        fields=["name", "product"],
    )
    fixed = 0
    for lot in lots:
        if not lot.product:
            continue
        rule = frappe.db.get_value("Lot Naming Rule", {"product": lot.product}, "name")
        if rule:
            frappe.db.set_value("Root Lot", lot.name, "naming_rule", rule,
                                update_modified=False)
            fixed += 1
    if fixed:
        print(f"  ✓ backfilled naming_rule on {fixed} Root Lot(s)")


# ---------------------------------------------------------------------------
# Bug 5 — rename rules off the product-based autoname
# ---------------------------------------------------------------------------

def _rename_rules_off_product_autoname():
    rules = frappe.get_all("Lot Naming Rule", fields=["name", "product"])
    renamed = 0
    for r in rules:
        if r.name.startswith("LNR-"):
            continue
        product = r.product  # save BEFORE rename — rename may overwrite it
        new_name = _next_lnr_name()
        # rev 2: no ignore_permissions kwarg (unsupported in this version)
        frappe.rename_doc("Lot Naming Rule", r.name, new_name, force=True)
        # If autoname was still field:product at rename time, the product
        # field now holds new_name. Restore the real product.
        frappe.db.set_value("Lot Naming Rule", new_name, "product", product,
                            update_modified=False)
        renamed += 1
        print(f"  ✓ renamed '{r.name}' -> {new_name} (product kept: {product})")
    if not renamed:
        print("  ✓ all rules already on LNR-#### naming")


def _next_lnr_name():
    existing = frappe.get_all(
        "Lot Naming Rule", filters={"name": ["like", "LNR-%"]}, pluck="name",
    )
    max_n = 0
    for n in existing:
        try:
            max_n = max(max_n, int(n.split("-", 1)[1]))
        except (IndexError, ValueError):
            continue
    return f"LNR-{max_n + 1:05d}"


# ---------------------------------------------------------------------------
# rev 2 — repair rules whose product was overwritten by earlier failed runs
# ---------------------------------------------------------------------------

def _repair_corrupted_products():
    """A product value like 'LNR-07434' (or equal to the doc's own name) is
    not an Item — it was overwritten by a rename under field:product autoname.
    Recover the real product from linked Root Lots, the legacy Lot Trace
    Profile, or the yarns table."""
    rules = frappe.get_all("Lot Naming Rule", fields=["name", "product"])
    for r in rules:
        corrupted = (
            not r.product
            or r.product == r.name
            or (r.product.startswith("LNR-") and not frappe.db.exists("Item", r.product))
        )
        if not corrupted:
            continue

        recovered = _recover_product(r.name)
        if recovered:
            frappe.db.set_value("Lot Naming Rule", r.name, "product", recovered,
                                update_modified=False)
            print(f"  ✓ repaired product on {r.name}: {recovered}")
        else:
            # Can't recover automatically: deactivate so it can't misfire,
            # flag for manual review instead of guessing.
            frappe.db.set_value("Lot Naming Rule", r.name, "active", 0,
                                update_modified=False)
            print(f"  ⚠ {r.name}: product unrecoverable — rule DEACTIVATED, "
                  f"set the correct Product manually and re-activate")


def _recover_product(rule_name):
    # 1) A Root Lot created from this rule still holds the product.
    p = frappe.db.get_value("Root Lot", {"naming_rule": rule_name}, "product")
    if p and frappe.db.exists("Item", p):
        return p

    # 2) Legacy Lot Trace Profile sharing a yarn with this rule.
    yarns = frappe.get_all(
        "Lot Naming Rule Yarn", filters={"parent": rule_name}, pluck="yarn_item",
    )
    if yarns and frappe.db.exists("DocType", "Lot Trace Item"):
        ti = frappe.get_all(
            "Lot Trace Item", filters={"yarn_item": ["in", yarns]},
            fields=["parent"], limit=1,
        )
        if ti:
            p = frappe.db.get_value("Lot Trace Profile", ti[0].parent, "product")
            if p and frappe.db.exists("Item", p):
                return p

    # 3) Legacy Phase 5 rule with the same yarn in its yarn_item field.
    if yarns:
        meta = frappe.get_meta("Lot Naming Rule")
        if meta.get_field("yarn_item"):
            other = frappe.get_all(
                "Lot Naming Rule",
                filters={"yarn_item": ["in", yarns], "name": ["!=", rule_name]},
                fields=["product"], limit=1,
            )
            if other and other[0].product and frappe.db.exists("Item", other[0].product):
                return other[0].product

    return None
