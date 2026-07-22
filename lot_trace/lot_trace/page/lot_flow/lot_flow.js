// Lot Flow Chart: one row per Root Lot, one column per process stage.
// Data source: lot_trace.api.flow.get_lot_flow

frappe.pages["lot-flow"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lot Flow"),
		single_column: true,
	});

	const state = { sales_order: null, product: null, root_lot: null };

	page.add_field({
		fieldname: "sales_order", label: __("Sales Order"),
		fieldtype: "Link", options: "Sales Order",
		change() { state.sales_order = this.get_value(); load(); },
	});
	page.add_field({
		fieldname: "product", label: __("Product"),
		fieldtype: "Link", options: "Item",
		change() { state.product = this.get_value(); load(); },
	});
	page.add_field({
		fieldname: "root_lot", label: __("Root Lot"),
		fieldtype: "Link", options: "Root Lot",
		change() { state.root_lot = this.get_value(); load(); },
	});
	page.set_secondary_action(__("Refresh"), () => load(), "refresh");

	const $body = $('<div class="lot-flow-body" style="padding:15px;"></div>')
		.appendTo(page.main);

	function badge(status) {
		const color = { "Open": "blue", "In Process": "orange",
			"Completed": "green", "Cancelled": "red" }[status] || "gray";
		return `<span class="indicator-pill ${color}">${frappe.utils.escape_html(status || "")}</span>`;
	}

	function cellHtml(cell) {
		if (!cell) return '<span class="text-muted">—</span>';
		let html = `<div style="line-height:1.35">
			<div><b>${cell.balance}</b> <small>${frappe.utils.escape_html(cell.uom || "")}</small></div>
			<div class="small text-muted">${__("In")} ${cell.in_qty} · ${__("Out")} ${cell.out_qty}</div>`;
		if (cell.first_voucher) {
			const v = cell.first_voucher;
			const more = cell.voucher_count > 1
				? ` <span class="text-muted">+${cell.voucher_count - 1}</span>` : "";
			html += `<div class="small">
				<a href="/app/${frappe.router.slug(v.voucher_type)}/${encodeURIComponent(v.voucher_no)}">
				${frappe.utils.escape_html(v.voucher_no)}</a>${more}</div>`;
		}
		(cell.sold_to || []).forEach((s) => {
			html += `<div class="small text-warning">@ ${frappe.utils.escape_html(s.party)}: ${s.qty}</div>`;
		});
		return html + "</div>";
	}

	function load() {
		frappe.call({
			method: "lot_trace.api.flow.get_lot_flow",
			args: state,
			freeze: false,
			callback(r) { render(r.message || { stages: [], rows: [], totals: {} }); },
		});
	}

	function render(data) {
		const t = data.totals || {};
		let html = `
		<div class="row" style="margin-bottom:15px;">
			${[["yarn_received", __("Yarn Received (kg)")],
			   ["yarn_in_process", __("Yarn In Process (kg)")],
			   ["weaved_pcs", __("Weaved (pcs)")],
			   ["fg_qty", __("Finished Goods")],
			   ["dispatched", __("Dispatched")],
			   ["open_exceptions", __("Open Exceptions")]].map(([k, label]) => `
				<div class="col-sm-2">
					<div class="frappe-card" style="padding:10px;text-align:center;">
						<div style="font-size:1.3em;font-weight:600;">${t[k] != null ? t[k] : 0}</div>
						<div class="small text-muted">${label}</div>
					</div>
				</div>`).join("")}
		</div>`;

		if (!data.rows.length) {
			html += `<div class="text-muted" style="padding:30px;text-align:center;">
				${__("No lots found. Adjust filters or receive yarn to create lots.")}</div>`;
			$body.html(html);
			return;
		}

		html += `<div style="overflow-x:auto;"><table class="table table-bordered" style="min-width:900px;">
			<thead><tr>
				<th>${__("Lot")}</th><th>${__("Product")}</th><th>${__("Status")}</th>
				${data.stages.map((s) =>
					`<th title="${frappe.utils.escape_html(s.stage_name)}">${frappe.utils.escape_html(s.name)}</th>`
				).join("")}
			</tr></thead><tbody>`;

		data.rows.forEach((row) => {
			const exc = row.open_exceptions
				? ` <span class="indicator-pill red">${row.open_exceptions} !</span>` : "";
			html += `<tr>
				<td><a href="/app/root-lot/${encodeURIComponent(row.lot)}">${frappe.utils.escape_html(row.lot)}</a>${exc}
					<div class="small text-muted">${row.received_qty} ${frappe.utils.escape_html(row.uom || "")}</div></td>
				<td>${frappe.utils.escape_html(row.product || "")}
					${row.sales_order ? `<div class="small"><a href="/app/sales-order/${encodeURIComponent(row.sales_order)}">${frappe.utils.escape_html(row.sales_order)}</a></div>` : ""}</td>
				<td>${badge(row.status)}
					<div class="small text-muted">${frappe.utils.escape_html(row.current_stage || "")}</div></td>
				${data.stages.map((s) => `<td>${cellHtml(row.cells[s.name])}</td>`).join("")}
			</tr>`;
		});

		html += "</tbody></table></div>";
		$body.html(html);
	}

	load();
};
