# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document


class RootLot(Document):
    def validate(self):
        # keep header totals honest even on manual edits
        try:
            from lot_trace.events.lot_factory_v2 import _apply_derived
            _apply_derived(self)
        except Exception:
            # never block a save because of a totals hiccup
            frappe.log_error(frappe.get_traceback(),
                             "Root Lot totals recompute failed")
