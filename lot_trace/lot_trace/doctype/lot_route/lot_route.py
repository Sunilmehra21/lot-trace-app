import frappe
from frappe import _
from frappe.model.document import Document


class LotRoute(Document):
	def validate(self):
		seen = set()
		for row in self.stages:
			if row.stage in seen:
				frappe.throw(_("Stage {0} appears more than once in the route")
					.format(row.stage))
			seen.add(row.stage)
