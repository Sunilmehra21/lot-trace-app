# -*- coding: utf-8 -*-
# Phase 6 — Extend the Root Lot doctype with production-run fields.
# Root Lot is OUR doctype (not ERP core), but we add fields via Custom Field so
# existing installs upgrade cleanly without a full doctype overwrite.

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    fields = {
        "Root Lot": [
            {
                "fieldname": "lot_code",
                "label": "Lot Code",
                "fieldtype": "Data",
                "insert_after": "naming_series" if _has_field("Root Lot", "naming_series") else None,
                "read_only": 1,
                "unique": 1,
            },
            {
                "fieldname": "profile",
                "label": "Lot Trace Profile",
                "fieldtype": "Link",
                "options": "Lot Trace Profile",
                "insert_after": "lot_code",
                "read_only": 1,
            },
            {
                "fieldname": "serial",
                "label": "Serial",
                "fieldtype": "Int",
                "insert_after": "profile",
                "read_only": 1,
            },
            {
                "fieldname": "period_mmyy",
                "label": "Period (MMYY)",
                "fieldtype": "Data",
                "insert_after": "serial",
                "read_only": 1,
            },
            {
                "fieldname": "intake_complete",
                "label": "Intake Complete",
                "fieldtype": "Check",
                "insert_after": "period_mmyy",
                "description": "All profile yarns received. Lot no longer accepts new NT yarns.",
            },
            {
                "fieldname": "section_lot_receipts",
                "label": "Yarn Receipts",
                "fieldtype": "Section Break",
                "insert_after": "intake_complete",
            },
            {
                "fieldname": "lot_receipts",
                "label": "Lot Receipts",
                "fieldtype": "Table",
                "options": "Lot Receipt",
                "insert_after": "section_lot_receipts",
            },
        ],
    }
    # Drop any None insert_after (field may not exist on older installs).
    for _dt, flist in fields.items():
        for f in flist:
            if f.get("insert_after") is None:
                f.pop("insert_after", None)

    create_custom_fields(fields, ignore_validate=True)
    frappe.db.commit()
    print("✓ Phase 6 fields ensured on Root Lot")


def _has_field(doctype, fieldname):
    meta = frappe.get_meta(doctype)
    return bool(meta.get_field(fieldname))
