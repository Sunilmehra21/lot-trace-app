frappe.pages["lot-trace-tree"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lot Trace Tree"),
		single_column: true,
	});
	new LotTraceTree(page);
};

class LotTraceTree {
	constructor(page) {
		this.page = page;
		this.direction = "fwd";
		this.data = null;
		this.make_filters();
		this.make_body();
	}

	make_filters() {
		this.lot_field = this.page.add_field({
			fieldname: "root_lot",
			label: __("Root Lot"),
			fieldtype: "Link",
			options: "Root Lot",
			change: () => this.refresh(),
		});
		this.page.add_inner_button(__("Forward (yarn → FG)"), () => {
			this.direction = "fwd";
			this.render();
		});
		this.page.add_inner_button(__("Backward (FG → yarn)"), () => {
			this.direction = "back";
			this.render();
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
	}

	make_body() {
		this.$body = $(`
			<div class="ltt-layout">
				<div class="ltt-tree"><div class="ltt-empty text-muted">
					${__("Select a Root Lot to render its trace tree")}</div></div>
				<div class="ltt-side"></div>
			</div>`).appendTo(this.page.main);
	}

	refresh() {
		const root_lot = this.lot_field.get_value();
		if (!root_lot) return;
		frappe.call({
			method: "lot_trace.api.tree.get_trace_tree",
			args: { root_lot },
			callback: (r) => {
				this.data = r.message;
				this.render();
			},
		});
	}

	render() {
		if (!this.data) return;
		const nodes = [...this.data.nodes];
		if (this.direction === "back") nodes.reverse();
		this.render_tree(nodes);
		this.render_side(this.data.lot, this.data.nodes);
	}

	stage_class(stage) {
		const map = { NT: "st-nt", DY: "st-dy", WV: "st-wv", FG: "st-fg" };
		return map[stage] || "st-mid";
	}

	render_tree(nodes) {
		const $tree = this.$body.find(".ltt-tree").empty();
		const title =
			this.direction === "fwd"
				? __("Forward trace — where did this yarn go?")
				: __("Backward trace — which material made these goods?");
		$tree.append(`<h5 class="ltt-title">${title}</h5>`);

		let $parent = $(`<ul class="ltt-root"></ul>`).appendTo($tree);
		nodes.forEach((n) => {
			const loss =
				n.expected_loss_pct && n.in_qty && n.out_qty
					? (((n.in_qty - n.out_qty) / n.in_qty) * 100).toFixed(1)
					: null;
			const movs = n.movements
				.map(
					(m) => `
				<a class="ltt-doc" href="/app/${frappe.router.slug(m.voucher_type)}/${encodeURIComponent(m.voucher_no)}">
					<span class="${m.qty > 0 ? "ltt-in" : "ltt-out"}">${m.qty > 0 ? "+" : "−"}${Math.abs(m.qty)}</span>
					${frappe.utils.escape_html(m.voucher_no)}
				</a>`
				)
				.join("");
			const $li = $(`
				<li>
					<div class="ltt-card">
						<div class="ltt-row1">
							<a class="ltt-code" href="/app/batch/${encodeURIComponent(n.batch)}">
								${frappe.utils.escape_html(n.batch)}</a>
							<span class="ltt-stage ${this.stage_class(n.stage)}">
								${frappe.utils.escape_html(n.stage)} · ${frappe.utils.escape_html(n.stage_name)}</span>
							${loss !== null ? `<span class="ltt-loss">loss ${loss}% (tol ${n.expected_loss_pct}%)</span>` : ""}
						</div>
						<div class="ltt-row2">
							<span>${frappe.utils.escape_html(n.item_name)}</span>
							<span>In: <b>${n.in_qty}</b> ${n.uom}</span>
							<span>Out: <b>${n.out_qty}</b> ${n.uom}</span>
							<span>Balance: <b>${n.balance}</b> ${n.uom}</span>
						</div>
						<div class="ltt-row3">${movs}</div>
					</div>
				</li>`);
			$parent.append($li);
			const $next = $(`<ul class="ltt-branch"></ul>`).appendTo($li);
			$parent = $next;
		});
	}

	render_side(lot, nodes) {
		const $side = this.$body.find(".ltt-side").empty();
		$side.append(`
			<div class="ltt-panel">
				<h6>${__("Root Lot")}</h6>
				<div class="ltt-kv"><span>${__("Lot")}</span><b>${frappe.utils.escape_html(lot.name)}</b></div>
				<div class="ltt-kv"><span>${__("Product")}</span><b>${frappe.utils.escape_html(lot.product || "")}</b></div>
				<div class="ltt-kv"><span>${__("Supplier")}</span><b>${frappe.utils.escape_html(lot.supplier || "")}</b></div>
				<div class="ltt-kv"><span>${__("Stage")}</span><b>${frappe.utils.escape_html(lot.current_stage || "")}</b></div>
				<div class="ltt-kv"><span>${__("Status")}</span><b>${frappe.utils.escape_html(lot.status || "")}</b></div>
				<div class="ltt-kv"><span>${__("Open exceptions")}</span>
					<b class="${lot.open_exceptions ? "text-danger" : "text-success"}">${lot.open_exceptions}</b></div>
			</div>
			<div class="ltt-panel">
				<h6>${__("Stage summary")}</h6>
				${nodes
					.map(
						(n) => `<div class="ltt-kv">
					<span class="ltt-stage ${this.stage_class(n.stage)}">${n.stage}</span>
					<b>${n.in_qty} ${n.uom}</b></div>`
					)
					.join("")}
			</div>`);
	}
}
