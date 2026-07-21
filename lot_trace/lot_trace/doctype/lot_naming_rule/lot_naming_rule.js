// V7 — Lot Naming Rule form: lock identity fields once the rule has been
// used to create a Root Lot. The server enforces this too (validate);
// this JS just makes the lock visible instead of surprising the user
// with an error on save. Only "Active" stays editable.

frappe.ui.form.on("Lot Naming Rule", {
    refresh(frm) {
        if (frm.is_new()) return;

        frappe.call({
            method: "lot_trace.lot_trace.doctype.lot_naming_rule.lot_naming_rule.get_lot_count",
            args: { rule: frm.doc.name },
            callback(r) {
                const lots = r.message || 0;
                if (!lots) return;

                ["product", "lot_code_prefix", "yarns"].forEach((f) =>
                    frm.set_df_property(f, "read_only", 1));
                // also stop row add/remove on the child table
                frm.set_df_property("yarns", "cannot_add_rows", true);
                frm.set_df_property("yarns", "cannot_delete_rows", true);

                frm.set_intro(
                    __("This rule is locked: {0} Root Lot(s) were created with it. Product, Prefix and Yarns can no longer be changed. To change the setup, untick Active and create a new rule.",
                        [lots]),
                    "orange"
                );

                frm.add_custom_button(__("View Root Lots"), () => {
                    frappe.set_route("List", "Root Lot",
                        { naming_rule: frm.doc.name });
                });
            },
        });
    },
});
