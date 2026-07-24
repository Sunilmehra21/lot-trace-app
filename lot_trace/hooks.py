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
        "on_cancel": "lot_trace.events.purchase_receipt.on_cancel",
    },
    "Subcontracting Receipt": {
        "before_submit": "lot_trace.events.subcontracting_receipt.before_submit",
        "on_submit": "lot_trace.events.subcontracting_receipt.on_submit",
    },
    "Stock Entry": {
        "before_submit": "lot_trace.events.stock_entry.before_submit",
    },
    "Delivery Note": {
        "before_submit": "lot_trace.events.delivery.before_submit",
        "on_submit": "lot_trace.events.delivery.on_submit",
        "on_cancel": "lot_trace.events.delivery.on_cancel",
    },
    "Sales Invoice": {
        "before_submit": "lot_trace.events.delivery.before_submit",
        "on_submit": "lot_trace.events.delivery.on_submit",
        "on_cancel": "lot_trace.events.delivery.on_cancel",
    },
    # pre-wired for the already-built custom repair doctypes
    # (harmless if the doctype names differ - configure in Lot Trace Settings
    #  and add matching doc_events in the repair app if names differ)
    "Repair Issue": {
        "before_submit": "lot_trace.events.repair.before_submit",
    },
    "Repair Receipt": {
        "before_submit": "lot_trace.events.repair.before_submit",
    },
}
# Root Lot LIST view -> "Create from Stock" + bulk "Delete Lot (cleanup)"
doctype_list_js = {
    "Root Lot": "public/js/root_lot_list.js",
}

# Root Lot FORM view -> single "Delete Lot (cleanup)" button
doctype_js = {
    "Root Lot": "public/js/root_lot_form.js",
}