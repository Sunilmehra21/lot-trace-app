// Root Lot form: "Delete Lot (cleanup)" + "View Trace" buttons.
// (Root Lot is not submittable, so delete — not cancel — is the removal action.)

frappe.ui.form.on("Root Lot", {
    refresh(frm) {
        if (frm.is_new()) return;

        frm.add_custom_button(__("View Trace"), () => {
            frappe.set_route("lot-trace-tree", { root_lot: frm.doc.name });
        });

        frm.add_custom_button(__("Delete Lot (cleanup)"), () => {
            frappe.confirm(
                __("Delete this Root Lot? Its batches and stock documents are kept — only lot links are removed. This cannot be undone."),
                () => {
                    frappe.call({
                        method: "lot_trace.api.cleanup.delete_root_lot",
                        args: { root_lot: frm.doc.name },
                        freeze: true,
                        freeze_message: __("Detaching links and deleting..."),
                        callback(r) {
                            if (r.message) {
                                frappe.show_alert({ message: r.message.message,
                                    indicator: "green" }, 7);
                                frappe.set_route("List", "Root Lot");
                            }
                        },
                    });
                }
            );
        }).addClass("btn-danger");
    },
});
