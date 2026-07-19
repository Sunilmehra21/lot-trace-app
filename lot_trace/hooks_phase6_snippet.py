# -*- coding: utf-8 -*-
# Phase 6 — doc_events wiring.
#
# Merge this block into your existing lot_trace/hooks.py. It registers the
# Phase 6 handlers on the standard ERPNext stock documents. We use before_submit
# (to set batch_no before stock posts) and on_cancel (to roll back our records).

doc_events = {
    "Purchase Receipt": {
        "before_submit": "lot_trace.events.purchase_receipt.before_submit",
        "on_cancel": "lot_trace.events.purchase_receipt.on_cancel",
    },
    "Subcontracting Receipt": {
        "before_submit": "lot_trace.events.subcontracting_receipt.before_submit",
    },
}

# Patches are declared in patches.txt:
#   lot_trace.patches.v6_0_add_custom_fields
#   lot_trace.patches.v6_0_extend_root_lot
#   lot_trace.patches.v6_0_migrate_naming_rules_to_profiles
