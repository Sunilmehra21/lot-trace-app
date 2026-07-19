// Root Lot List: "Create from Stock" button
// Adds a button to create a new Root Lot from existing warehouse inventory

frappe.listview_settings['Root Lot'] = {
    add_fields: ["name", "status"],
    filters: [["disabled", "=", false]],
    onload: function(listview) {
        listview.page.add_action_item(__("Create from Stock"), function() {
            show_create_from_stock_dialog();
        });
    }
};

function show_create_from_stock_dialog() {
    const dialog = new frappe.ui.Dialog({
        title: "Create Root Lot from Stock",
        fields: [
            {
                label: "Item",
                fieldname: "item_code",
                fieldtype: "Link",
                options: "Item",
                reqd: 1,
                description: "Select a yarn/fabric item from your warehouse"
            },
            {
                label: "Warehouse",
                fieldname: "warehouse",
                fieldtype: "Link",
                options: "Warehouse",
                reqd: 1,
                description: "Warehouse where this item is currently stored"
            },
            {
                label: "Quantity",
                fieldname: "qty",
                fieldtype: "Float",
                reqd: 1,
                precision: 2,
                description: "Amount to allocate to this lot (in item's UOM)"
            },
            {
                label: "Product (Optional)",
                fieldname: "product",
                fieldtype: "Link",
                options: "Product",
                description: "If not set, will use product from Lot Naming Rule"
            },
        ],
        primary_action_label: "Create Lot",
        primary_action(values) {
            frappe.call({
                method: "lot_trace.api.create_from_stock.create_root_lot_from_stock",
                args: {
                    item_code: values.item_code,
                    warehouse: values.warehouse,
                    qty: values.qty,
                    product: values.product || null
                },
                callback: function(r) {
                    if (r.message) {
                        frappe.msgprint({
                            title: "Success",
                            message: r.message.message,
                            indicator: "green"
                        });
                        dialog.hide();
                        // Refresh the list
                        cur_list.refresh();
                        // Navigate to the new Root Lot
                        frappe.set_route("Form", "Root Lot", r.message.root_lot);
                    }
                },
                error: function(r) {
                    frappe.msgprint({
                        title: "Error",
                        message: r.responseJSON.message || "Failed to create lot",
                        indicator: "red"
                    });
                }
            });
        }
    });
    dialog.show();
}
