# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document


class LotNamingRule(Document):
    def validate(self):
        self._one_active_rule_per_product()
        self._yarn_table_sane()
        self._lock_after_first_lot()

    def on_trash(self):
        if self._lot_count():
            frappe.throw(
                f"Cannot delete this rule: {self._lot_count()} Root Lot(s) "
                f"were created with it. Deactivate it instead (untick "
                f"Active) if you no longer want to use it.")

    # ------------------------------------------------------------- locking

    def _lot_count(self):
        if self.is_new():
            return 0
        return frappe.db.count("Root Lot", {"naming_rule": self.name})

    def _lock_after_first_lot(self):
        """Once a Root Lot exists for this rule, its identity is frozen:
        product, lot code prefix and the yarns table can no longer change —
        otherwise existing lot codes / batch names would stop matching
        their rule. Only the Active checkbox stays editable."""
        lots = self._lot_count()
        if not lots:
            return

        before = self.get_doc_before_save()
        if not before:
            return

        locked = []
        if self.product != before.product:
            locked.append("Product (Finished Good)")
        if self.lot_code_prefix != before.lot_code_prefix:
            locked.append("Lot Code Prefix")
        if self._yarns_signature(self) != self._yarns_signature(before):
            locked.append("Yarns table")

        if locked:
            frappe.throw(
                f"This rule is LOCKED: {lots} Root Lot(s) have already been "
                f"created with it, so these fields can no longer be changed: "
                f"<b>{', '.join(locked)}</b>.<br><br>"
                f"If the product setup has genuinely changed, untick "
                f"<b>Active</b> on this rule and create a NEW rule for the "
                f"product — existing lots keep their history intact.",
                title="Lot Naming Rule is locked")

    @staticmethod
    def _yarns_signature(doc):
        return sorted(
            (y.yarn_item or "", y.role or "", (y.item_abbr or "").strip())
            for y in (doc.get("yarns") or []))

    # ---------------------------------------------------------- base rules

    def _one_active_rule_per_product(self):
        if not self.active:
            return
        other = frappe.db.get_value(
            "Lot Naming Rule",
            {"product": self.product, "active": 1,
             "name": ["!=", self.name]},
            "name")
        if other:
            frappe.throw(
                f"Product {self.product} already has an active rule "
                f"({other}). Deactivate it first or edit that rule.")

    def _yarn_table_sane(self):
        if not self.yarns:
            frappe.throw("Add at least one yarn to the Yarns table.")
        primaries = [y for y in self.yarns
                     if (y.role or "Primary") == "Primary"]
        if len(primaries) != 1:
            frappe.throw(
                "Exactly ONE yarn must have role = Primary "
                "(the yarn whose receipt creates a new lot). "
                "All other yarns must be Secondary.")
        seen = set()
        for y in self.yarns:
            if y.yarn_item in seen:
                frappe.throw(f"Yarn {y.yarn_item} is listed twice.")
            seen.add(y.yarn_item)
            if not (y.item_abbr or "").strip():
                frappe.throw(f"Row {y.idx}: Abbr is required "
                             f"(used in batch names, e.g. 'A').")
            other_rule = frappe.db.get_value(
                "Lot Naming Rule Yarn",
                {"yarn_item": y.yarn_item, "parent": ["!=", self.name],
                 "parenttype": "Lot Naming Rule"},
                "parent")
            if other_rule and frappe.db.get_value(
                    "Lot Naming Rule", other_rule, "active"):
                frappe.throw(
                    f"Yarn {y.yarn_item} is already used by active rule "
                    f"{other_rule}. A yarn can belong to only one active "
                    f"rule, otherwise receipts would be ambiguous.")


@frappe.whitelist()
def get_lot_count(rule):
    """Used by the form JS to grey out locked fields."""
    return frappe.db.count("Root Lot", {"naming_rule": rule})
