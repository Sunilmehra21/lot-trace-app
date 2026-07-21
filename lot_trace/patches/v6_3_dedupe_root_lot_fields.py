# -*- coding: utf-8 -*-
# Phase 6.3 — Remove duplicate fields on Root Lot.
#
# Cause: the v6_0_extend_root_lot patch added fields (lot_code, serial, ...)
# as Custom Fields, but the Root Lot doctype JSON also defines lot_code as a
# standard field -> "Fieldname lot_code appears multiple times in rows 8, 8".
#
# Fix: delete any Custom Field on Root Lot whose fieldname already exists as
# a standard field of the doctype. Idempotent.

import frappe


def execute():
    meta_fields = {
        df.fieldname
        for df in frappe.get_meta("Root Lot", cached=False).fields
    }
    # get_meta includes custom fields too, so read standard fields directly:
    standard = set(frappe.get_all(
        "DocField", filters={"parent": "Root Lot"}, pluck="fieldname",
    ))

    custom = frappe.get_all(
        "Custom Field",
        filters={"dt": "Root Lot"},
        fields=["name", "fieldname"],
    )

    removed = 0
    for cf in custom:
        if cf.fieldname in standard:
            frappe.delete_doc("Custom Field", cf.name,
                              ignore_permissions=True, force=True)
            removed += 1
            print(f"  ✓ removed duplicate Custom Field: {cf.fieldname}")

    frappe.clear_cache(doctype="Root Lot")
    print(f"✓ Root Lot dedupe complete ({removed} duplicate(s) removed)"
          if removed else "✓ no duplicates found on Root Lot")
