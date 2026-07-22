// Order Lot Overview report filters.

frappe.query_reports["Order Lot Overview"] = {
	filters: [
		{
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "status",
			label: __("Lot Status"),
			fieldtype: "Select",
			options: "\nOpen\nIn Process\nCompleted\nCancelled",
		},
	],
};
