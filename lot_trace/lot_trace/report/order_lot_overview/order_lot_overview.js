frappe.query_reports["Order Lot Overview"] = {
    filters: [
        {fieldname: "sales_order", label: __("Sales Order"), fieldtype: "Link",
         options: "Sales Order"},
        {fieldname: "product", label: __("Product"), fieldtype: "Link", options: "Item"},
        {fieldname: "status", label: __("Status"), fieldtype: "Select",
         options: "\nOpen\nIn Process\nCompleted\nShort Closed"},
    ],
};
