// V7 — Lot Flow Chart: stage grid per lot + summary cards.
// Data: lot_trace.api.dashboard.get_flow_chart

frappe.pages["lot-flow-chart"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper, title: __("Lot Flow Chart"), single_column: true,
    });

    const filters = {};
    const mkfield = (fieldname, label, options) =>
        page.add_field({
            fieldname, label, fieldtype: "Link", options,
            change() { filters[fieldname] = this.get_value(); load(); },
        });
    mkfield("sales_order", __("Sales Order"), "Sales Order");
    mkfield("product", __("Product"), "Item");
    mkfield("root_lot", __("Root Lot"), "Root Lot");
    page.set_primary_action(__("Refresh"), load, "refresh");

    const $body = $('<div class="lot-flow-body" style="padding:10px 0">')
        .appendTo(page.main);

    function load() {
        frappe.call({
            method: "lot_trace.api.dashboard.get_flow_chart",
            args: filters,
            callback: (r) => render(r.message || {}),
        });
    }

    function fmt(v) { return frappe.format(v || 0, { fieldtype: "Float" }); }

    function render(data) {
        const stages = data.stages || [];
        const lots = data.lots || [];
        const s = data.summary || {};

        let grid = '<div style="overflow-x:auto"><table class="table" ' +
            'style="min-width:900px"><thead><tr><th></th>';
        stages.forEach((st, i) => {
            grid += `<th style="text-align:center">${i + 1} · ` +
                `${frappe.utils.escape_html(st.label)}<br>` +
                `<small class="text-muted">${st.code}</small></th>`;
        });
        grid += "</tr></thead><tbody>";

        if (!lots.length) {
            grid += `<tr><td colspan="${stages.length + 1}" ` +
                `class="text-muted text-center">${__("No lots found")}</td></tr>`;
        }
        lots.forEach((lot) => {
            grid += `<tr><td><a href="/app/root-lot/` +
                `${encodeURIComponent(lot.name)}"><b>${frappe.utils
                    .escape_html(lot.lot_code || lot.name)}</b></a><br>` +
                `<small class="text-muted">${__("Status")}: ` +
                `${lot.status || ""}</small></td>`;
            stages.forEach((st) => {
                const q = (lot.stage_qty || {})[st.code] || 0;
                const active = lot.current_stage === st.code;
                grid += `<td style="text-align:center;` +
                    (active ? "background:#fff3cd;" : "") +
                    `">${q ? "<b>" + fmt(q) + "</b>" : '<span class="text-muted">—</span>'}</td>`;
            });
            grid += "</tr>";
        });
        grid += "</tbody></table></div>";

        const card = (label, value, sub) =>
            `<div style="flex:1;min-width:150px;border:1px solid var(--border-color);` +
            `border-radius:8px;padding:12px;margin:4px">` +
            `<div class="text-muted" style="font-size:11px;text-transform:uppercase">${label}</div>` +
            `<div style="font-size:20px;font-weight:600">${value}</div>` +
            (sub ? `<small class="text-muted">${sub}</small>` : "") + "</div>";

        const cards =
            '<div style="display:flex;flex-wrap:wrap;margin-top:8px">' +
            card(__("Yarn Received"), fmt(s.yarn_received_kg) + " Kg",
                (s.lot_count || 0) + " " + __("lots")) +
            card(__("Yarn In Process"), fmt(s.in_process_kg) + " Kg",
                __("NT + DY balances")) +
            card(__("Weaved Pcs Received"), fmt(s.weaved_pcs) + " Pcs") +
            card(__("Finished Goods"), fmt(s.finished_qty) + " Nos") +
            card(__("Dispatched"), fmt(s.dispatched_qty) + " Nos") +
            card(__("Open Exceptions"), (s.open_exceptions || 0) +
                (s.open_exceptions ? " ⚠" : " ✓")) +
            "</div>";

        $body.html(grid + cards);
    }

    load();
};
