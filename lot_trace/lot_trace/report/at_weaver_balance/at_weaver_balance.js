// At Weaver Balance report filters.

frappe.query_reports["At Weaver Balance"] = {
	filters: [
		{
			fieldname: "root_lot",
			label: __("Root Lot"),
			fieldtype: "Link",
			options: "Root Lot",
		},
		{
			fieldname: "weaver",
			label: __("Weaver (Customer)"),
			fieldtype: "Link",
			options: "Customer",
			get_query() {
				return { filters: { represents_supplier: 1 } };
			},
		},
	],
};
