# -*- coding: utf-8 -*-
# Phase 6.1 — Simplify: Lot Trace Profile → Lot Naming Rule
#
# Converts complex Lot Trace Profile records into simpler Lot Naming Rule format.
# Non-destructive: keeps old profiles read-only as backup.

import re
import frappe


def execute():
    """Migrate Lot Trace Profile → Lot Naming Rule (simplified)."""

    # Do we have the old Profile doctype?
    if not frappe.db.exists("DocType", "Lot Trace Profile"):
        print("No Lot Trace Profile doctype; skipping conversion.")
        return

    profiles = frappe.get_all(
        "Lot Trace Profile",
        filters={"active": 1},
        fields=["name", "product", "lot_code_pattern"],
    )

    if not profiles:
        print("No active Lot Trace Profiles to convert.")
        return

    converted = 0
    for profile in profiles:
        # Skip if Lot Naming Rule already exists for this product
        if frappe.db.exists("Lot Naming Rule", {"product": profile.product}):
            continue

        # Extract lot code prefix from pattern (e.g., MV/BG from MV/BG/{MMYY}/{##})
        prefix = _extract_prefix(profile.lot_code_pattern)

        # Create new Lot Naming Rule
        rule = frappe.get_doc({
            "doctype": "Lot Naming Rule",
            "product": profile.product,
            "active": 1,
            "lot_code_prefix": prefix,
            "lot_route": None,  # User will set this manually if needed
        })

        # Copy yarns from Trace Items table
        trace_items = frappe.get_all(
            "Lot Trace Item",
            filters={"parent": profile.name},
            fields=["yarn_item", "role", "item_abbr"],
        )

        for ti in trace_items:
            rule.append("yarns", {
                "yarn_item": ti.yarn_item,
                "role": ti.role,
                "item_abbr": ti.item_abbr or "",
            })

        rule.insert(ignore_permissions=True)
        converted += 1
        print(f"  ✓ {profile.product}: created Lot Naming Rule from Profile")

    frappe.db.commit()
    print(f"✓ Phase 6.1 migration: {converted} Lot Naming Rule(s) created. "
          f"Old Lot Trace Profiles kept read-only.")


def _extract_prefix(pattern):
    """Extract the prefix from pattern: MV/BG from MV/BG/{MMYY}/{##}."""
    if not pattern:
        return "MV/BG"
    # Match up to (but not including) the first { token
    m = re.match(r"^([^{]+)", pattern)
    if m:
        prefix = m.group(1).rstrip("/")
        return prefix
    return pattern.rstrip("/{#}")
