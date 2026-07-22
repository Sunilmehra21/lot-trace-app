# -*- coding: utf-8 -*-
import frappe
from frappe.model.document import Document


class RootLot(Document):
    def validate(self):
        # Totals engine wiring (Phase 3): recompute derived quantities from
        # the Lot Receipts child table + live Stock Ledger balances.
        # Guarded import so Phase 2 installs cleanly before events/ exists.
        try:
            from lot_trace.events.lot_factory import apply_derived
        except ImportError:
            return
        apply_derived(self)
