# -*- coding: utf-8 -*-
# Phase 6.2 HOTFIX — hooks.py doc_events block.
#
# REPLACE the entire doc_events dict in your lot_trace/hooks.py with this.
# (Bug 2 happened because hooks still referenced on_submit handlers that the
# V2 files didn't define. The new handler files define every hook name below,
# so this wiring can never raise AttributeError again.)

doc_events = {
    "Purchase Receipt": {
        "before_submit": "lot_trace.events.purchase_receipt.before_submit",
        "on_submit": "lot_trace.events.purchase_receipt.on_submit",
        "before_cancel": "lot_trace.events.purchase_receipt.before_cancel",
        "on_cancel": "lot_trace.events.purchase_receipt.on_cancel",
    },
    "Subcontracting Receipt": {
        "before_submit": "lot_trace.events.subcontracting_receipt.before_submit",
        "on_submit": "lot_trace.events.subcontracting_receipt.on_submit",
        "before_cancel": "lot_trace.events.subcontracting_receipt.before_cancel",
        "on_cancel": "lot_trace.events.subcontracting_receipt.on_cancel",
    },
    "Root Lot": {
        "before_cancel": "lot_trace.events.root_lot_cleanup.before_cancel",
        "on_trash": "lot_trace.events.root_lot_cleanup.on_trash",
    },
}
