frappe.query_reports["Root Lot Trace"] = {
    filters: [
        {
            fieldname: "root_lot",
            label: __("Root Lot"),
            fieldtype: "Link",
            options: "Root Lot",
            reqd: 1,
        },
    ],
};
