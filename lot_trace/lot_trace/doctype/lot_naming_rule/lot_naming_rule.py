# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document


class LotNamingRule(Document):
    def validate(self):
        self._one_active_rule_per_product()
        self._yarn_table_sane()
        self._lock_after_first_lot()

    def on_trash(self):
        if self._lot_count():
            frappe.throw(_(
                "Cannot delete this rule: {0} Root Lot(s) were created with "
                "it. Deactivate it instead (untick Active) if you no longer "
                "want to use it.").format(self._lot_count()))

    # ------------------------------------------------------------- locking

    def _lot_count(self):
        if self.is_new():
            return 0
        return frappe.db.count("Root Lot", {"naming_rule": self.name})

    def _lock_after_first_lot(self):
        """Once a Root Lot exists for this rule its identity is frozen:
        product, prefix, route and the yarns table can no longer change —
        otherwise existing lot codes / batch names would stop matching.
        Only the Active checkbox stays editable."""
        lots = self._lot_count()
        if not lots:
            return
        before = self.get_doc_before_save()
        if not before:
            return

        locked = []
        if self.product != before.product:
            locked.append(_("Product (Finished Good)"))
        if self.lot_code_prefix != before.lot_code_prefix:
            locked.append(_("Lot Code Prefix"))
        if (self.route or "") != (before.route or ""):
            locked.append(_("Lot Route"))
        if self._yarns_signature(self) != self._yarns_signature(before):
            locked.append(_("Yarns table"))

        if locked:
            frappe.throw(_(
                "This rule is LOCKED: {0} Root Lot(s) have already been "
                "created with it, so these fields can no longer be changed: "
                "<b>{1}</b>.<br><br>If the product setup has genuinely "
                "changed, untick <b>Active</b> on this rule and create a NEW "
                "rule for the product — existing lots keep their history."
            ).format(lots, ", ".join(locked)),
                title=_("Lot Naming Rule is locked"))

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
            {"product": self.product, "active": 1, "name": ["!=", self.name]},
            "name")
        if other:
            frappe.throw(_(
                "Product {0} already has an active rule ({1}). "
                "Deactivate it first or edit that rule."
            ).format(self.product, other))

    def _yarn_table_sane(self):
        if not self.yarns:
            frappe.throw(_("Add at least one yarn to the Yarns table."))
        primaries = [y for y in self.yarns
                     if (y.role or "Primary") == "Primary"]
        if len(primaries) != 1:
            frappe.throw(_(
                "Exactly ONE yarn must have role = Primary (the yarn whose "
                "receipt creates a new lot). All other yarns must be "
                "Secondary."))
        seen = set()
        for y in self.yarns:
            if y.yarn_item in seen:
                frappe.throw(_("Yarn {0} is listed twice.").format(y.yarn_item))
            seen.add(y.yarn_item)
            if not (y.item_abbr or "").strip():
                frappe.throw(_(
                    "Row {0}: Abbr is required (used in batch names, "
                    "e.g. 'A').").format(y.idx))
            other_rule = frappe.db.get_value(
                "Lot Naming Rule Yarn",
                {"yarn_item": y.yarn_item, "parent": ["!=", self.name],
                 "parenttype": "Lot Naming Rule"},
                "parent")
            if other_rule and frappe.db.get_value(
                    "Lot Naming Rule", other_rule, "active"):
                frappe.throw(_(
                    "Yarn {0} is already used by active rule {1}. A yarn can "
                    "belong to only one active rule, otherwise receipts "
                    "would be ambiguous.").format(y.yarn_item, other_rule))


@frappe.whitelist()
def get_lot_count(rule):
    """Used by the form JS to grey out locked fields."""
    frappe.has_permission("Lot Naming Rule", "read", throw=True)
    return frappe.db.count("Root Lot", {"naming_rule": rule})
