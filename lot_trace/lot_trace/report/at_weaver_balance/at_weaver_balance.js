frappe.query_reports["At-Weaver Balance"] = {
	filters: [
		{
			fieldname: "weaver",
			label: __("Weaver (Supplier)"),
			fieldtype: "Link",
			options: "Supplier",
		},
		{
			fieldname: "root_lot",
			label: __("Root Lot"),
			fieldtype: "Link",
			options: "Root Lot",
		},
	],
};
