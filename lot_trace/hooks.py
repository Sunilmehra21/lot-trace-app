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
# --- Hotfix 6.3: Root Lot buttons ---------------------------------------
# LIST view -> "Create from Stock" + bulk "Delete Lot (cleanup)"
doctype_list_js = {
    "Root Lot": "public/js/root_lot_list.js",
}

# FORM view -> single "Delete Lot (cleanup)" button
doctype_js = {
    "Root Lot": "public/js/root_lot_form.js",
}
