// Purchase Receipt: "Auto-Fill Lot Consumption" for multi-lot weaving PRs.
// Allocates dyed yarn across lots from the item's BOM (at-weaver balances).

frappe.ui.form.on("Purchase Receipt", {
    refresh(frm) {
        if (frm.doc.docstatus !== 0) return;
        if (!frm.fields_dict.lot_consumption) return;

        frm.add_custom_button(__("Auto-Fill Lot Consumption"), () => {
            const row = (frm.doc.items || [])[0];
            if (!row) {
                frappe.msgprint(__("Add the weaved item row first."));
                return;
            }
            frappe.call({
                method: "lot_trace.api.lot.suggest_lot_consumption",
                args: {
                    purchase_receipt: frm.doc.name,
                    item_code: row.item_code,
                    qty_pcs: row.qty,
                },
                freeze: true,
                freeze_message: __("Allocating dyed yarn from lots..."),
                callback(r) {
                    const rows = r.message || [];
                    if (!rows.length) {
                        frappe.msgprint(__(
                            "No allocation could be suggested. Check that the item has a BOM with dyed yarn and that dyed yarn was sent to the weaver."));
                        return;
                    }
                    frm.clear_table("lot_consumption");
                    rows.forEach((a) => {
                        const d = frm.add_child("lot_consumption");
                        d.root_lot = a.root_lot;
                        d.dyed_yarn_item = a.dyed_yarn_item;
                        d.qty_kg = a.qty_kg;
                    });
                    frm.refresh_field("lot_consumption");
                    frappe.show_alert({
                        message: __("Filled {0} consumption row(s).", [rows.length]),
                        indicator: "green",
                    }, 5);
                },
            });
        }, __("Lot Trace"));
    },
});
