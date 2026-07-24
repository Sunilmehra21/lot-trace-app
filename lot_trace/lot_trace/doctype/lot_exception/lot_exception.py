import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class LotException(Document):
    def validate(self):
        if self.resolved and not self.resolved_by:
            self.resolved_by = frappe.session.user
            self.resolved_on = now_datetime()
        if not self.resolved:
            self.resolved_by = None
            self.resolved_on = None
