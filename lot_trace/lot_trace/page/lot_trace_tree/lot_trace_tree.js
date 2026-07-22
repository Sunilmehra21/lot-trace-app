// Lot Trace Tree: Root Lot -> stage batches -> stock movements.
// Data source: lot_trace.api.tree.get_lot_tree
// Opened from Root Lot form "View Trace" (route options) or directly.

frappe.pages["lot-trace-tree"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lot Trace Tree"),
		single_column: true,
	});

	const lot_field = page.add_field({
		fieldname: "root_lot", label: __("Root Lot"),
		fieldtype: "Link", options: "Root Lot", reqd: 1,
		change() { load(this.get_value()); },
	});
	page.set_secondary_action(__("Refresh"), () =>
		load(lot_field.get_value()), "refresh");

	const $body = $('<div class="lot-tree-body" style="padding:15px;"></div>')
		.appendTo(page.main);

	function esc(v) { return frappe.utils.escape_html(String(v == null ? "" : v)); }

	function load(root_lot) {
		if (!root_lot) {
			$body.html(`<div class="text-muted" style="padding:30px;text-align:center;">
				${__("Select a Root Lot to view its trace.")}</div>`);
			return;
		}
		frappe.call({
			method: "lot_trace.api.tree.get_lot_tree",
			args: { root_lot },
			callback(r) { render(r.message || {}); },
		});
	}

	function render(data) {
		if (!data.lot) {
			$body.html(`<div class="text-muted" style="padding:30px;text-align:center;">
				${__("Lot not found.")}</div>`);
			return;
		}
		const lot = data.lot;
		let html = `
		<div class="frappe-card" style="padding:15px;margin-bottom:15px;">
			<h4 style="margin-top:0;">
				<a href="/app/root-lot/${encodeURIComponent(lot.name)}">${esc(lot.lot_code || lot.name)}</a>
				<span class="indicator-pill ${{"Open": "blue", "In Process": "orange",
					"Completed": "green", "Cancelled": "red"}[lot.status] || "gray"}">${esc(lot.status)}</span>
			</h4>
			<div class="row small">
				<div class="col-sm-3"><b>${__("Product")}:</b> ${esc(lot.product)}</div>
				<div class="col-sm-2"><b>${__("Stage")}:</b> ${esc(lot.current_stage)}</div>
				<div class="col-sm-2"><b>${__("Received")}:</b> ${lot.received_qty || 0} ${esc(lot.uom)}</div>
				<div class="col-sm-2"><b>${__("Weaved")}:</b> ${lot.weaved_pcs || 0} pcs</div>
				<div class="col-sm-3"><b>${__("FG / Dispatched")}:</b> ${lot.fg_qty || 0} / ${lot.dispatched_qty || 0}</div>
			</div>
			${lot.sales_order ? `<div class="small"><b>${__("Sales Order")}:</b>
				<a href="/app/sales-order/${encodeURIComponent(lot.sales_order)}">${esc(lot.sales_order)}</a></div>` : ""}
		</div>`;

		if (!(data.batches || []).length) {
			html += `<div class="text-muted" style="padding:20px;text-align:center;">
				${__("No batches yet for this lot.")}</div>`;
		}

		(data.batches || []).forEach((b, i) => {
			const cid = "lot-tree-batch-" + i;
			html += `
			<div class="frappe-card" style="padding:12px;margin-bottom:10px;margin-left:25px;">
				<div style="cursor:pointer;" data-toggle-target="${cid}">
					<b>${esc(b.stage)}</b> ·
					<a href="/app/batch/${encodeURIComponent(b.batch)}">${esc(b.batch)}</a>
					<span class="text-muted">— ${esc(b.item)}</span>
					<span class="pull-right float-right"><b>${__("Balance")}: ${b.balance}</b>
						<span class="text-muted small">(${b.movements.length} ${__("movements")})</span></span>
				</div>
				<div id="${cid}" style="display:none;margin-top:10px;">
					<table class="table table-bordered table-sm small" style="margin:0;">
						<thead><tr><th>${__("Date")}</th><th>${__("Voucher")}</th>
							<th>${__("Warehouse")}</th><th class="text-right">${__("Qty")}</th></tr></thead>
						<tbody>
						${b.movements.map((m) => `<tr>
							<td>${esc(m.date)}</td>
							<td><a href="/app/${frappe.router.slug(m.voucher_type)}/${encodeURIComponent(m.voucher_no)}">
								${esc(m.voucher_type)}: ${esc(m.voucher_no)}</a></td>
							<td>${esc(m.warehouse)}</td>
							<td class="text-right ${m.qty < 0 ? "text-danger" : "text-success"}">
								${m.qty} ${esc(m.uom)}</td>
						</tr>`).join("")}
						</tbody>
					</table>
				</div>
			</div>`;
		});

		$body.html(html);
		$body.find("[data-toggle-target]").on("click", function () {
			$("#" + $(this).attr("data-toggle-target")).slideToggle(150);
		});
	}

	// Accept route options from Root Lot form "View Trace" button
	// (works on first load and on every later navigation to this page).
	wrapper.lot_trace_apply_route = function () {
		const opts = frappe.route_options || {};
		if (opts.root_lot) {
			frappe.route_options = null;
			lot_field.set_value(opts.root_lot);
			load(opts.root_lot);
		}
	};

	wrapper.lot_trace_apply_route();
	if (!lot_field.get_value()) load(null);
};

frappe.pages["lot-trace-tree"].on_page_show = function (wrapper) {
	if (wrapper.lot_trace_apply_route) wrapper.lot_trace_apply_route();
};
