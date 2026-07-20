# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — Lot Naming Rule controller.
# Legacy Phase 5 fields removed; validation simplified.

from datetime import datetime

import frappe
from frappe.model.document import Document


class LotNamingRule(Document):
    def validate(self):
        self._validate_yarns()
        self._validate_prefix()

    def _validate_yarns(self):
        if not self.yarns:
            frappe.throw("Add at least one yarn in the Yarns table.")

        primaries = [y for y in self.yarns if y.role == "Primary"]
        if len(primaries) != 1:
            frappe.throw("Exactly one yarn must have Role = Primary.")

        abbrs = [(y.item_abbr or "").strip().upper() for y in self.yarns]
        if "" in abbrs:
            frappe.throw("Abbr is mandatory for every yarn.")
        if len(abbrs) != len(set(abbrs)):
            frappe.throw("Abbr values must be unique across all yarns.")

        items = [y.yarn_item for y in self.yarns]
        if len(items) != len(set(items)):
            frappe.throw("The same yarn item is listed more than once.")

    def _validate_prefix(self):
        if "{" in (self.lot_code_prefix or ""):
            frappe.throw("Lot Code Prefix should be plain text (e.g., MV/BG). "
                         "The serial and month are added automatically.")


def next_lot_serial_for_rule(rule_name):
    """Next serial for this rule in the current MMYY period."""
    mmyy = datetime.now().strftime("%m%y")
    existing = frappe.get_all(
        "Root Lot",
        filters={"naming_rule": rule_name, "period_mmyy": mmyy},
        fields=["serial"],
        order_by="serial desc",
        limit=1,
    )
    if existing and existing[0].serial:
        return int(existing[0].serial) + 1
    return 1


def generate_lot_code(rule_name, prefix=None):
    """Next lot code: {prefix}/{MMYY}/{serial:02d}."""
    if not prefix:
        prefix = frappe.db.get_value("Lot Naming Rule", rule_name, "lot_code_prefix")
    mmyy = datetime.now().strftime("%m%y")
    serial = next_lot_serial_for_rule(rule_name)
    return f"{prefix}/{mmyy}/{serial:02d}"
