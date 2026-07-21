# -*- coding: utf-8 -*-

app_name = "lot_trace"
app_title = "Lot Trace"
app_publisher = "Rangsutra"
app_description = "Lot traceability for textile manufacturing (yarn - dyeing - weaving - cutting)"
app_email = "sunil.mehra@rangsutra.com"
app_license = "MIT"

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
