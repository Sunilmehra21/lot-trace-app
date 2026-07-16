frappe.pages["lot-flow"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Lot Flow Chart"),
		single_column: true,
	});
	new LotFlowChart(page);
};

const LOT_COLORS = ["#5e35b1", "#00796b", "#ad5700", "#1565c0", "#ad1457",
	"#37474f", "#6a1b9a", "#2e7d32"];

class LotFlowChart {
	constructor(page) {
		this.page = page;
		this.make_filters();
		this.$body = $(`<div class="lfc-wrap">
			<div class="lfc-empty text-muted">
				${__("Pick a Sales Order / Product / Root Lot and press Refresh")}</div>
		</div>`).appendTo(this.page.main);
		this.refresh();
	}

	make_filters() {
		this.so_field = this.page.add_field({
			fieldname: "sales_order",
			label: __("Sales Order"),
			fieldtype: "Link",
			options: "Sales Order",
			change: () => this.refresh(),
		});
		this.product_field = this.page.add_field({
			fieldname: "product",
			label: __("Product"),
			fieldtype: "Link",
			options: "Item",
			change: () => this.refresh(),
		});
		this.lot_field = this.page.add_field({
			fieldname: "root_lot",
			label: __("Root Lot"),
			fieldtype: "Link",
			options: "Root Lot",
			change: () => this.refresh(),
		});
		this.page.set_primary_action(__("Refresh"), () => this.refresh());
	}

	refresh() {
		frappe.call({
			method: "lot_trace.api.flow.get_lot_flow",
			args: {
				sales_order: this.so_field.get_value() || null,
				product: this.product_field.get_value() || null,
				root_lot: this.lot_field.get_value() || null,
			},
			callback: (r) => this.render(r.message),
		});
	}

	render(data) {
		this.$body.empty();
		if (!data || !data.rows.length) {
			this.$body.append(`<div class="lfc-empty text-muted">
				${__("No root lots found for these filters")}</div>`);
			return;
		}
		const stages = data.stages;
		const cols = `170px repeat(${stages.length}, minmax(130px, 1fr))`;

		const $board = $(`<div class="lfc-board"></div>`).appendTo(this.$body);

		// stage header row
		const $head = $(`<div class="lfc-grid" style="grid-template-columns:${cols}">
			<div></div></div>`).appendTo($board);
		stages.forEach((s, i) => {
			$head.append(`<div class="lfc-stagehead ${s.name === "FG" ? "lfc-fin" : ""}
				${["DY", "WV"].includes(s.name) ? "lfc-ext" : ""}">
				${i + 1} · ${frappe.utils.escape_html(s.stage_name || s.name)}
				<small>${frappe.utils.escape_html(s.name)}</small></div>`);
		});

		// one row per lot
		data.rows.forEach((row, idx) => {
			const color = LOT_COLORS[idx % LOT_COLORS.length];
			const $row = $(`<div class="lfc-grid" style="grid-template-columns:${cols}">
			</div>`).appendTo($board);
			const exc = row.open_exceptions
				? `<span class="lfc-exc">⚠ ${row.open_exceptions}</span>` : "";
			$row.append(`
				<div class="lfc-lotlabel" style="background:${color}">
					<a href="/app/root-lot/${encodeURIComponent(row.lot)}">${frappe.utils.escape_html(row.lot)}</a>
					<small>${frappe.utils.escape_html(row.supplier || "")}<br>
					${__("Status")}: ${frappe.utils.escape_html(row.status || "")} ${exc}</small>
				</div>`);

			stages.forEach((s, si) => {
				const c = row.cells[s.name];
				if (!c || (!c.in_qty && !c.out_qty)) {
					$row.append(`<div class="lfc-cell lfc-cellempty"></div>`);
					return;
				}
				const doc = c.first_voucher
					? `<a class="lfc-doc"
						href="/app/${frappe.router.slug(c.first_voucher.voucher_type)}/${encodeURIComponent(c.first_voucher.voucher_no)}">
						${frappe.utils.escape_html(c.first_voucher.voucher_no)}${c.voucher_count > 1 ? " +" + (c.voucher_count - 1) : ""}</a>`
					: "";
				const custody = (c.sold_to || [])
					.map((st) => `<span class="lfc-cust">📍 ${frappe.utils.escape_html(st.party)} · ${st.qty}</span>`)
					.join("");
				const arrow = si < stages.length - 1 ? `<span class="lfc-arrow">➤</span>` : "";
				const is_current = row.current_stage === s.name;
				$row.append(`
					<div class="lfc-cell ${is_current ? "lfc-current" : ""}" style="border-left-color:${color}">
						<span class="lfc-batch">…${frappe.utils.escape_html(s.name)}</span>
						<span class="lfc-qty"><b>${c.in_qty}</b> ${c.uom}
							${c.balance !== c.in_qty ? ` · ${__("bal")} ${c.balance}` : ""}</span>
						${custody}
						${doc}
						${is_current ? `<span class="lfc-chip">${__("CURRENT")}</span>` : ""}
						${arrow}
					</div>`);
			});
		});

		// summary strip
		const t = data.totals;
		$(`<div class="lfc-summary">
			<div class="lfc-sumcard"><h5>${__("Yarn received")}</h5>
				<div class="lfc-big">${t.yarn_received} Kg</div>
				<div class="lfc-sub">${data.rows.length} ${__("lots")}</div></div>
			<div class="lfc-sumcard"><h5>${__("Yarn in process")}</h5>
				<div class="lfc-big">${t.yarn_in_process} Kg</div>
				<div class="lfc-sub">${__("NT + DY balances")}</div></div>
			<div class="lfc-sumcard"><h5>${__("Weaved pcs received")}</h5>
				<div class="lfc-big">${t.weaved_pcs} Pcs</div></div>
			<div class="lfc-sumcard"><h5>${__("Finished goods")}</h5>
				<div class="lfc-big">${t.fg_qty} Nos</div></div>
			<div class="lfc-sumcard"><h5>${__("Dispatched")}</h5>
				<div class="lfc-big">${t.dispatched} Nos</div></div>
			<div class="lfc-sumcard"><h5>${__("Open exceptions")}</h5>
				<div class="lfc-big" style="color:${t.open_exceptions ? "#b26a00" : "#2e7d32"}">
					${t.open_exceptions}${t.open_exceptions ? " ⚠" : " ✓"}</div></div>
		</div>`).appendTo($board);
	}
}
