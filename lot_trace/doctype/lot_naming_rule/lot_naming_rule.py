# -*- coding: utf-8 -*-
# Phase 6 V2 — Lot Naming Rule (simplified, no complex tokens)

import re
from datetime import datetime
import frappe
from frappe.model.document import Document


class LotNamingRule(Document):
    def validate(self):
        self._validate_yarns()
        self._validate_prefix()

    def _validate_yarns(self):
        """Ensure exactly one primary yarn if yarns table is used."""
        if not self.yarns:
            # Backward compat: Phase 5 single-yarn rule (yarn_item field)
            if not self.yarn_item:
                frappe.throw("Add at least one yarn in the Yarns table, "
                             "or use the legacy Yarn Item field for single-yarn products.")
            return

        primaries = [y for y in self.yarns if y.role == "Primary"]
        if len(primaries) != 1:
            frappe.throw("Exactly one yarn must have Role = Primary.")

        abbrs = [y.item_abbr for y in self.yarns if y.item_abbr]
        if len(abbrs) != len(set(abbrs)):
            frappe.throw("Item Abbr values must be unique across all yarns.")

    def _validate_prefix(self):
        """Ensure prefix is sensible (no tokens)."""
        if "{" in (self.lot_code_prefix or "") or "}" in (self.lot_code_prefix or ""):
            frappe.throw("Lot Code Prefix should be simple (e.g., MV/BG). "
                         "Do not use {MMYY}, {##}, or other tokens. "
                         "Serial is auto-generated.")


def next_lot_serial_for_rule(rule_name):
    """Get next serial for this rule in the current MMYY period."""
    mmyy = datetime.now().strftime("%m%y")
    existing = frappe.get_all(
        "Root Lot",
        filters={"naming_rule": rule_name, "period_mmyy": mmyy},
        fields=["serial"],
        order_by="serial desc",
        limit=1,
    )
    return (int(existing[0].serial) + 1) if existing else 1


def generate_lot_code(rule_name, prefix=None):
    """Generate the next lot code for a rule: {prefix}/{MMYY}/{##serial}."""
    if not prefix:
        prefix = frappe.db.get_value("Lot Naming Rule", rule_name, "lot_code_prefix")
    mmyy = datetime.now().strftime("%m%y")
    serial = next_lot_serial_for_rule(rule_name)
    return f"{prefix}/{mmyy}/{serial:02d}"
