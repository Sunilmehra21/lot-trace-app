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
		this.all_expanded = true;
		this.make_filters();
		this.make_body();
	}

	make_filters() {
		this.so_field = this.page.add_field({
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
			change: () => this.auto_pick_lot(),
		});
		this.product_field = this.page.add_field({
			fieldname: "product",
			label: __("Product"),
			fieldtype: "Link",
			options: "Item",
			change: () => this.auto_pick_lot(),
		});
		this.lot_field = this.page.add_field({
			fieldname: "root_lot",
			label: __("Root Lot"),
			fieldtype: "Link",
			options: "Root Lot",
			change: () => this.refresh(),
		});
		this.lot_field.df.get_query = () => {
			const f = {};
			if (this.so_field.get_value()) f.sales_order = this.so_field.get_value();
			if (this.product_field.get_value()) f.product = this.product_field.get_value();
			return { filters: f };
		};
		this.page.add_inner_button(__("Forward (yarn → FG)"), () => {
			this.direction = "fwd";
			this.render();
		});
		this.page.add_inner_button(__("Backward (FG → yarn)"), () => {
			this.direction = "back";
			this.render();
		});
		this.expand_btn = this.page.add_inner_button(__("Collapse All"), () =>
			this.toggle_all()
		);
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
	}

	auto_pick_lot() {
		const filters = {};
		if (this.so_field.get_value()) filters.sales_order = this.so_field.get_value();
		if (this.product_field.get_value()) filters.product = this.product_field.get_value();
		if (!Object.keys(filters).length) return;
		frappe.db.get_list("Root Lot", { filters, limit: 2 }).then((rows) => {
			if (rows.length === 1) this.lot_field.set_value(rows[0].name);
		});
	}

	make_body() {
		this.$body = $(`
			<div class="ltt-layout">
				<div class="ltt-tree"><div class="ltt-empty text-muted">
					${__("Select a Root Lot (or filter by Sales Order / Product) to render its trace tree")}</div></div>
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
				this.all_expanded = true;
				this.expand_btn.text(__("Collapse All"));
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

	toggle_all() {
		this.all_expanded = !this.all_expanded;
		this.$body
			.find("ul.ltt-branch")
			.toggleClass("ltt-hidden", !this.all_expanded);
		this.$body
			.find(".ltt-toggler:not(.ltt-leaf)")
			.text(this.all_expanded ? "−" : "+");
		this.expand_btn.text(this.all_expanded ? __("Collapse All") : __("Expand All"));
	}

	stage_class(stage) {
		// every stage has its own distinct color
		const map = {
			NT: "st-nt",
			DY: "st-dy",
			WV: "st-wv",
			CT: "st-ct",
			ST: "st-st",
			EM: "st-em",
			FN: "st-fn",
			PK: "st-pk",
			FG: "st-fg",
		};
		return map[stage] || "st-mid";
	}

	movement_chip(m) {
		const url = `/app/${frappe.router.slug(m.voucher_type)}/${encodeURIComponent(m.voucher_no)}`;
		if (m.is_transfer) {
			return `
				<a class="ltt-doc ltt-doc-xfer" href="${url}">
					<span class="ltt-xfer">⇄ ${Math.abs(m.qty)}</span>
					${frappe.utils.escape_html(m.voucher_no)}
					<span class="ltt-mvparty">${__("transfer")}</span>
				</a>`;
		}
		const party = m.party
			? `<span class="ltt-mvparty">· ${frappe.utils.escape_html(m.party)}</span>`
			: "";
		return `
			<a class="ltt-doc" href="${url}">
				<span class="${m.qty > 0 ? "ltt-in" : "ltt-out"}">${m.qty > 0 ? "+" : "−"}${Math.abs(m.qty)}</span>
				${frappe.utils.escape_html(m.voucher_no)} ${party}
			</a>`;
	}

	render_tree(nodes) {
		const $tree = this.$body.find(".ltt-tree").empty();
		const title =
			this.direction === "fwd"
				? __("Forward trace — where did this yarn go?")
				: __("Backward trace — which material made these goods?");
		$tree.append(`<h5 class="ltt-title">${title}</h5>`);

		let $parent = $(`<ul class="ltt-root"></ul>`).appendTo($tree);
		nodes.forEach((n, i) => {
			const seen = new Set();
			const movs = n.movements
				.filter((m) => {
					const key = m.voucher_type + "|" + m.voucher_no;
					if (m.is_transfer && seen.has(key)) return false;
					seen.add(key);
					return true;
				})
				.map((m) => this.movement_chip(m))
				.join("");
			const loss_badge =
				n.loss_qty !== null && n.loss_qty !== undefined
					? `<span class="ltt-loss ${n.loss_over ? "ltt-loss-bad" : ""}">
						loss ${n.loss_qty} ${n.uom} (${n.loss_pct}%)${n.loss_over ? " ⚠" : " ✓"}</span>`
					: "";
			const merge_chips = (n.merged_from || [])
				.map(
					(m) => `<span class="ltt-merge">⨁ ${__("merged from")}
						<a href="#" onclick="return false;">${frappe.utils.escape_html(m.root_lot)}</a>
						· ${m.qty_kg} Kg</span>`
				)
				.join("");
			const has_child = i < nodes.length - 1;
			const $li = $(`
				<li>
					<div class="ltt-node">
						<div class="ltt-toggler ${has_child ? "" : "ltt-leaf"}">${has_child ? "−" : "·"}</div>
						<div class="ltt-card">
							<div class="ltt-row1">
								<a class="ltt-code" href="/app/batch/${encodeURIComponent(n.batch)}">
									${frappe.utils.escape_html(n.batch)}</a>
								<span class="ltt-stage ${this.stage_class(n.stage)}">
									${frappe.utils.escape_html(n.stage)} · ${frappe.utils.escape_html(n.stage_name)}</span>
								${loss_badge}
							</div>
							<div class="ltt-row2">
								<span>${frappe.utils.escape_html(n.item_name)}</span>
								<span>In: <b>${n.in_qty}</b> ${n.uom}</span>
								<span>Out: <b>${n.out_qty}</b> ${n.uom}</span>
								<span>Balance: <b>${n.balance}</b> ${n.uom}</span>
							</div>
							${merge_chips ? `<div class="ltt-row3">${merge_chips}</div>` : ""}
							<div class="ltt-row3">${movs}</div>
						</div>
					</div>
				</li>`);
			$li.find(".ltt-toggler:not(.ltt-leaf)").on("click", function () {
				const $ul = $(this).closest("li").children("ul.ltt-branch");
				const hidden = $ul.toggleClass("ltt-hidden").hasClass("ltt-hidden");
				$(this).text(hidden ? "+" : "−");
			});
			// merged-from chips open the other lot in the tree
			$li.find(".ltt-merge a").each((_, a) => {
				const lot = $(a).text().trim();
				$(a).on("click", () => this.lot_field.set_value(lot));
			});
			$parent.append($li);
			const $next = $(`<ul class="ltt-branch"></ul>`).appendTo($li);
			$parent = $next;
		});
	}

	render_side(lot, nodes) {
		const $side = this.$body.find(".ltt-side").empty();

		const merged_into = (lot.merged_into || [])
			.map(
				(m) => `<div class="ltt-kv"><span>${__("Merged into")}</span>
					<b class="ltt-merge-link" data-lot="${frappe.utils.escape_html(m.root_lot)}">
					${frappe.utils.escape_html(m.root_lot)} (${m.qty_kg} Kg)</b></div>`
			)
			.join("");

		// TRUE progress = stages reached vs the lot's FULL planned route
		// (planned_stages from the Lot Route, or all active global stages).
		// The old formula divided by created batches only, so an unfinished
		// chain already showed 100%.
		const fg = flt(lot.fg_qty), disp = flt(lot.dispatched_qty);
		const planned = lot.planned_stages || [];
		const active_stages = new Set(
			nodes.filter((n) => n.in_qty > 0).map((n) => n.stage)
		);
		const done = planned.filter((s) => active_stages.has(s)).length;
		let pct = 0, prog_label = "";
		if (planned.length) {
			pct = Math.round((done / planned.length) * 100);
			prog_label = __("{0} of {1} planned stages reached", [done, planned.length]);
			if (fg > 0) {
				const dpct = Math.min(100, Math.round((disp / fg) * 100));
				prog_label += " · " + __("{0}% of FG dispatched", [dpct]);
			}
		} else {
			const active = nodes.filter((n) => n.in_qty > 0).length;
			pct = nodes.length ? Math.round((active / nodes.length) * 100) : 0;
			prog_label = __("{0} of {1} stages active", [active, nodes.length]);
		}
		const bar_color = pct >= 100 ? "#2e7d32" : pct > 0 ? "#2490ef" : "#eceff1";

		// stage progress rows: show ALL planned stages; pending ones greyed
		const node_by_stage = {};
		nodes.forEach((n) => (node_by_stage[n.stage] = n));
		const stage_rows = (planned.length ? planned : nodes.map((n) => n.stage))
			.map((s) => {
				const n = node_by_stage[s];
				if (n) {
					return `<div class="ltt-kv">
						<span><span class="ltt-stage ${this.stage_class(n.stage)}">${n.stage}</span>
							${frappe.utils.escape_html(n.stage_name)}</span>
						<b>${n.in_qty} ${n.uom}</b></div>`;
				}
				return `<div class="ltt-kv ltt-pending">
					<span><span class="ltt-stage st-pending">${frappe.utils.escape_html(s)}</span>
						${__("pending")}</span><b>—</b></div>`;
			})
			.join("");

		$side.append(`
			<div class="ltt-panel">
				<h6>${__("Root Lot")}</h6>
				<div class="ltt-kv"><span>${__("Lot")}</span><b>${frappe.utils.escape_html(lot.name)}</b></div>
				<div class="ltt-kv"><span>${__("Product")}</span><b>${frappe.utils.escape_html(lot.product || "")}</b></div>
				<div class="ltt-kv"><span>${__("Sales Order")}</span><b>${frappe.utils.escape_html(lot.sales_order || "")}</b></div>
				<div class="ltt-kv"><span>${__("Supplier")}</span><b>${frappe.utils.escape_html(lot.supplier || "")}</b></div>
				<div class="ltt-kv"><span>${__("Stage")}</span><b>${frappe.utils.escape_html(lot.current_stage || "")}</b></div>
				<div class="ltt-kv"><span>${__("Status")}</span><b>${frappe.utils.escape_html(lot.status || "")}</b></div>
				<div class="ltt-kv"><span>${__("Open exceptions")}</span>
					<b class="${lot.open_exceptions ? "text-danger" : "text-success"}">${lot.open_exceptions}</b></div>
				${merged_into}
			</div>
			<div class="ltt-panel">
				<h6>${__("Stage progress")}</h6>
				${stage_rows}
				<div class="ltt-prog"><div style="width:${pct}%;background:${bar_color}"></div></div>
				<div class="ltt-prog-label">${prog_label}</div>
			</div>
			<div class="ltt-panel">
				<h6>${__("Legend — stages")}</h6>
				<div class="ltt-legend">
					<span class="ltt-stage st-nt">NT</span>
					<span class="ltt-stage st-dy">DY</span>
					<span class="ltt-stage st-wv">WV</span>
					<span class="ltt-stage st-ct">CT</span>
					<span class="ltt-stage st-st">ST</span>
					<span class="ltt-stage st-em">EM</span>
					<span class="ltt-stage st-fn">FN</span>
					<span class="ltt-stage st-pk">PK</span>
					<span class="ltt-stage st-fg">FG</span>
				</div>
				<h6 style="margin-top:12px">${__("Markers")}</h6>
				<div class="ltt-legend">
					<span class="ltt-in">+ ${__("receipt")}</span>
					<span class="ltt-out">− ${__("issue/dispatch")}</span>
					<span class="ltt-xfer">⇄ ${__("transfer")}</span>
					<span class="ltt-loss">${__("loss vs BOM")}</span>
					<span class="ltt-merge">⨁ ${__("lot merge")}</span>
				</div>
			</div>`);

		$side.find(".ltt-merge-link").on("click", (e) => {
			this.lot_field.set_value($(e.currentTarget).data("lot"));
		});

		function flt(v) {
			return parseFloat(v) || 0;
		}
	}
}
