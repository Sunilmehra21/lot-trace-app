// Root Lot list buttons: "Create from Stock" + bulk "Delete Lot (cleanup)".

frappe.listview_settings["Root Lot"] = {
    onload(listview) {
        listview.page.add_inner_button(__("Create from Stock"), () => {
            const d = new frappe.ui.Dialog({
                title: __("Create Root Lot from Existing Stock"),
                fields: [
                    { fieldname: "item_code", label: __("Yarn Item"),
                      fieldtype: "Link", options: "Item", reqd: 1,
                      description: __("Must be in an active Lot Naming Rule.") },
                    { fieldname: "warehouse", label: __("Warehouse"),
                      fieldtype: "Link", options: "Warehouse", reqd: 1,
                      onchange() {
                          const item = d.get_value("item_code");
                          const wh = d.get_value("warehouse");
                          if (item && wh) {
                              frappe.db.get_value("Bin",
                                  { item_code: item, warehouse: wh },
                                  "actual_qty").then((r) => {
                                  const bal = (r.message && r.message.actual_qty) || 0;
                                  d.set_df_property("qty", "description",
                                      __("Available in warehouse: {0}", [bal]));
                              });
                          }
                      } },
                    { fieldname: "qty", label: __("Quantity"),
                      fieldtype: "Float", reqd: 1 },
                ],
                primary_action_label: __("Create Lot"),
                primary_action(values) {
                    frappe.call({
                        method: "lot_trace.api.create_from_stock.create_root_lot_from_stock",
                        args: values,
                        freeze: true,
                        freeze_message: __("Creating lot and repacking stock..."),
                        callback(r) {
                            if (r.message) {
                                frappe.show_alert({ message: r.message.message,
                                    indicator: "green" }, 7);
                                d.hide();
                                listview.refresh();
                                frappe.set_route("Form", "Root Lot", r.message.root_lot);
                            }
                        },
                    });
                },
            });
            d.show();
        });

        listview.page.add_actions_menu_item(__("Delete Lot (cleanup)"), () => {
            const selected = listview.get_checked_items(true);
            if (!selected.length) {
                frappe.msgprint(__("Select one or more Root Lots first."));
                return;
            }
            frappe.confirm(
                __("Delete {0} Root Lot(s)? Batches and stock documents are kept — only lot links are removed.",
                    [selected.length]),
                () => {
                    let done = 0;
                    frappe.dom.freeze(__("Deleting..."));
                    const next = (i) => {
                        if (i >= selected.length) {
                            frappe.dom.unfreeze();
                            frappe.show_alert({ message: __("Deleted {0} lot(s).", [done]),
                                indicator: "green" }, 5);
                            listview.refresh();
                            return;
                        }
                        frappe.call({
                            method: "lot_trace.api.cleanup.delete_root_lot",
                            args: { root_lot: selected[i] },
                            callback(r) { if (r.message) done += 1; next(i + 1); },
                            error() { next(i + 1); },
                        });
                    };
                    next(0);
                }
            );
        });
    },
};
