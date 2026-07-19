# -*- coding: utf-8 -*-
# Phase 6 — Lot Trace Profile controller
# Validates the profile: exactly one primary yarn, unique abbrs, valid tokens.

import re
import frappe
from frappe.model.document import Document


class LotTraceProfile(Document):
    def validate(self):
        self._validate_trace_items()
        self._validate_lot_code_pattern()
        self._validate_batch_rules()

    def _validate_trace_items(self):
        if not self.trace_items:
            frappe.throw("Add at least one yarn in Trace Items.")

        primaries = [r for r in self.trace_items if r.role == "Primary"]
        if len(primaries) == 0:
            frappe.throw("Exactly one Trace Item must have Role = Primary "
                         "(the yarn that triggers a new production lot).")
        if len(primaries) > 1:
            frappe.throw("Only one Primary yarn is allowed per profile. "
                         "Mark the others as Secondary.")

        # Unique, non-empty abbreviations.
        seen = {}
        for r in self.trace_items:
            abbr = (r.item_abbr or "").strip()
            if not abbr:
                frappe.throw(f"Item Abbr is mandatory for {r.yarn_item}.")
            key = abbr.upper()
            if key in seen:
                frappe.throw(f"Item Abbr '{abbr}' is used twice "
                             f"({seen[key]} and {r.yarn_item}). Abbrs must be unique.")
            seen[key] = r.yarn_item

            # Same yarn item should not appear twice.
        items = [r.yarn_item for r in self.trace_items]
        dupes = {i for i in items if items.count(i) > 1}
        if dupes:
            frappe.throw(f"Yarn item(s) listed more than once: {', '.join(dupes)}")

    def _validate_lot_code_pattern(self):
        if "{##" not in self.lot_code_pattern and "{#" not in self.lot_code_pattern:
            # allowed, but warn: serial will be appended
            frappe.msgprint(
                "Lot Code Pattern has no {##} serial token; a serial will be "
                "appended automatically to keep lot codes unique.",
                indicator="orange", alert=True,
            )

    def _validate_batch_rules(self):
        for r in (self.batch_naming_rules or []):
            if "{LOT}" not in (r.pattern or ""):
                frappe.throw(f"Batch pattern for stage {r.stage} must contain "
                             "the {LOT} token.")
