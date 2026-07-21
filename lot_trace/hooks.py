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

# Root Lot buttons
doctype_list_js = {
    "Root Lot": "public/js/root_lot_list.js",
}
doctype_js = {
    "Root Lot": "public/js/root_lot_form.js",
}

# Fixtures — shipped with the app, imported on install and every `bench migrate`.
# Filtered so `bench export-fixtures` only ever re-exports OUR records,
# never custom fields or roles belonging to other apps on the same site.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": {"module": "Lot Trace"},
    },
    {
        "dt": "Role",
        "filters": {"name": ["in", ["Lot Manager", "Lot User"]]},
    },
    "Lot Process Stage",
]
