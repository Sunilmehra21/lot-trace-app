// Purchase Receipt client helpers for lot traceability:
//  1. Root Lot pickers (item row + Lot Consumption table) show ONLY lots
//     whose dyed yarn was sold to this PR's supplier (weaver duality).
//  2. Lot Consumption: Dyed Yarn Item is filtered to the picked lot's DY
//     batches, and picking a lot fetches the LIVE availability with this
//     weaver (sold − already consumed) so the user can set qty accordingly.

frappe.ui.form.on("Purchase Receipt", {
	setup(frm) {
		// item row Root Lot: only lots reachable for this supplier
		frm.set_query("root_lot", "items", () => ({
			query: "lot_trace.api.lot.weaver_root_lot_query",
			filters: { supplier: frm.doc.supplier || "" },
		}));

		// Lot Consumption table: same supplier-aware lot list
		frm.set_query("root_lot", "lot_consumption", () => ({
			query: "lot_trace.api.lot.weaver_root_lot_query",
			filters: { supplier: frm.doc.supplier || "" },
		}));

		// Lot Consumption: dyed yarn item limited to the row's lot DY batches
		frm.set_query("dyed_yarn_item", "lot_consumption", (doc, cdt, cdn) => {
			const row = locals[cdt][cdn];
			return {
				query: "lot_trace.api.lot.dyed_item_query",
				filters: { root_lot: row.root_lot || "" },
			};
		});
	},
});

frappe.ui.form.on("Lot Consumption Detail", {
	root_lot(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.root_lot || !frm.doc.supplier) return;
		frappe.call({
			method: "lot_trace.api.lot.get_dyed_available",
			args: { root_lot: row.root_lot, supplier: frm.doc.supplier },
			callback: (r) => {
				const d = r.message || {};
				// auto-fill the dyed yarn item when the lot has exactly one
				if (d.item && !row.dyed_yarn_item) {
					frappe.model.set_value(cdt, cdn, "dyed_yarn_item", d.item);
				}
				// show the live availability on the row + as an alert
				frappe.model.set_value(cdt, cdn, "available_kg", d.available_kg);
				frappe.show_alert(
					{
						message: __(
							"Lot {0}: {1} kg dyed yarn available with {2} (sold {3} kg, consumed {4} kg)",
							[
								row.root_lot,
								d.available_kg,
								frm.doc.supplier,
								d.sold_kg,
								d.consumed_kg,
							]
						),
						indicator: d.available_kg > 0 ? "green" : "orange",
					},
					7
				);
			},
		});
	},

	qty_kg(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.qty_kg || row.available_kg === undefined || row.available_kg === null)
			return;
		if (flt(row.qty_kg) > flt(row.available_kg) + 0.1) {
			frappe.show_alert(
				{
					message: __(
						"Warning: lot {0} consumption {1} kg exceeds the {2} kg available with this weaver",
						[row.root_lot, row.qty_kg, row.available_kg]
					),
					indicator: "red",
				},
				7
			);
		}
	},
});
