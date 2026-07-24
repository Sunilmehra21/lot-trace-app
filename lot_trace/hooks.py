app_name = "lot_trace"
app_title = "Lot Trace"
app_publisher = "Rangsutra"
app_description = "Root Lot traceability on native Batch (greige yarn to finished garment)"
app_email = "sunil.mehra@rangsutra.com"
app_license = "MIT"
required_apps = ["erpnext"]

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Lot Manager", "Lot User"]]]},
    {"dt": "Custom Field", "filters": [["module", "=", "Lot Trace"]]},
    {"dt": "Lot Process Stage"},
]

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

doctype_list_js = {
    "Root Lot": "public/js/root_lot_list.js",
}

doctype_js = {
    "Purchase Receipt": "public/js/purchase_receipt.js",
    "Root Lot": "public/js/root_lot_form.js",
}
