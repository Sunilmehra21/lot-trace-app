# -*- coding: utf-8 -*-
# Phase 6 — Custom fields patch.
# Adds the link fields Phase 6 relies on. Idempotent (safe to re-run).
#
# We add fields via Custom Field so we do NOT modify any ERPNext core doctype
# schema files (user requirement #4 — don't customise core, only extend).

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    fields = {
        "Batch": [
            {
                "fieldname": "custom_root_lot",
                "label": "Root Lot",
                "fieldtype": "Link",
                "options": "Root Lot",
                "insert_after": "batch_id",
                "in_standard_filter": 1,
                "read_only": 1,
            },
            {
                "fieldname": "custom_stage",
                "label": "Lot Stage",
                "fieldtype": "Data",
                "insert_after": "custom_root_lot",
                "read_only": 1,
            },
        ],
        "Purchase Order": [
            {
                "fieldname": "custom_root_lot",
                "label": "Root Lot",
                "fieldtype": "Link",
                "options": "Root Lot",
                "insert_after": "project",
                "description": "Optional: pin secondary-yarn receipts of this PO to a lot.",
            },
        ],
        "Subcontracting Receipt Item": [
            {
                "fieldname": "custom_root_lot",
                "label": "Root Lot (override)",
                "fieldtype": "Link",
                "options": "Root Lot",
                "insert_after": "batch_no",
                "description": "Leave blank — resolved automatically from the consumed greige batch.",
            },
        ],
    }

    create_custom_fields(fields, ignore_validate=True)
    frappe.db.commit()
    print("✓ Phase 6 custom fields ensured on Batch, Purchase Order, "
          "Subcontracting Receipt Item")
