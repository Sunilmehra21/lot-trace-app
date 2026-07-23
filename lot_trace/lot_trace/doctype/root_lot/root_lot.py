import frappe
from frappe.model.document import Document


class RootLot(Document):
    def validate(self):
        if self.customer is None and self.sales_order:
            self.customer = frappe.db.get_value(
                "Sales Order", self.sales_order, "customer")
