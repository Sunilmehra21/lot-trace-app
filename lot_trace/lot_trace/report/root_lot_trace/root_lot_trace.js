// Root Lot Trace report filters.

frappe.query_reports["Root Lot Trace"] = {
	filters: [
		{
			fieldname: "root_lot",
			label: __("Root Lot"),
			fieldtype: "Link",
			options: "Root Lot",
		},
		{
			fieldname: "process_stage",
			label: __("Stage"),
			fieldtype: "Link",
			options: "Lot Process Stage",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
