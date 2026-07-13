import frappe
from frappe import _
from frappe.model.document import Document


class LotNamingRule(Document):
    def validate(self):
        if self.active and frappe.db.exists(
            "Lot Naming Rule",
            {"yarn_item": self.yarn_item, "product": self.product,
             "active": 1, "name": ["!=", self.name]}):
            frappe.throw(_("An active naming rule already exists for this "
                           "yarn item + product combination."))
        self.prefix = (self.prefix or "").strip().strip("/")
