# -*- coding: utf-8 -*-
import frappe
from frappe import _
from frappe.model.document import Document


class LotRoute(Document):
    def validate(self):
        seen = set()
        for row in self.stages or []:
            if row.stage in seen:
                frappe.throw(_(
                    "Stage {0} appears twice in the route.").format(row.stage))
            seen.add(row.stage)
        if not seen:
            frappe.throw(_("Add at least one stage to the route."))
