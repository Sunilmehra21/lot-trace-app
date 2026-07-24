# Generic hook for the already-built custom Repair Issue / Repair Receipt doctypes.
# Requirement: their item rows carry a `batch_no` field. The handler enforces the
# single-lot rule and stamps root_lot on rows that have that field.

import frappe

from lot_trace.events.common import (
    collect_root_lots, enforce_single_lot, get_root_lot_of_batch)


def before_submit(doc, method=None):
    lots = collect_root_lots(doc)
    enforce_single_lot(doc, lots)
    for row in doc.get("items") or []:
        if hasattr(row, "root_lot") and row.get("batch_no") and not row.get("root_lot"):
            row.root_lot = get_root_lot_of_batch(row.batch_no)
