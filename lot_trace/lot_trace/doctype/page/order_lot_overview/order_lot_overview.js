// V7 — Order Lot Overview: one row per lot with live totals.
// Data: lot_trace.api.dashboard.get_order_overview

frappe.pages["order-lot-overview"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper, title: __("Order Lot Overview"), single_column: true,
    });

    const filters = {};
    page.add_field({
        fieldname: "sales_order", label: __("Sales Order"),
        fieldtype: "Link", options: "Sales Order",
        change() { filters.sales_order = this.get_value(); load(); },
    });
    page.add_field({
        fieldname: "product", label: __("Product"),
        fieldtype: "Link", options: "Item",
        change() { filters.product = this.get_value(); load(); },
    });
    page.add_field({
        fieldname: "status", label: __("Status"), fieldtype: "Select",
        options: "\nOpen\nIn Process\nCompleted\nClosed",
        change() { filters.status = this.get_value(); load(); },
    });
    page.set_primary_action(__("Refresh"), load, "refresh");

    const $body = $('<div style="padding:10px 0">').appendTo(page.main);
    const esc = frappe.utils.escape_html;
    const fmt = (v) => frappe.format(v || 0, { fieldtype: "Float" });

    function load() {
        frappe.call({
            method: "lot_trace.api.dashboard.get_order_overview",
            args: filters,
            callback: (r) => render((r.message || {}).lots || []),
        });
    }

    function render(lots) {
        if (!lots.length) {
            $body.html(`<div class="text-muted text-center" style="padding:60px">
                ${__("Nothing to show")}</div>`);
            return;
        }
        let html = `<div style="overflow-x:auto"><table class="table table-bordered"
            style="min-width:1000px"><thead><tr>
            <th>${__("Root Lot")}</th><th>${__("Product")}</th>
            <th>${__("Sales Order")}</th><th>${__("Status")}</th>
            <th>${__("Stage")}</th><th>${__("Yarn Recd (Kg)")}</th>
            <th>${__("In Process (Kg)")}</th><th>${__("Weaved Pcs")}</th>
            <th>${__("Finished")}</th><th>${__("Dispatched")}</th>
            <th>${__("Batches")}</th></tr></thead><tbody>`;
        lots.forEach((l) => {
            html += `<tr>
                <td><a href="/app/root-lot/${encodeURIComponent(l.name)}">
                    <b>${esc(l.lot_code || l.name)}</b></a></td>
                <td>${esc(l.product || "")}</td>
                <td>${l.sales_order
                    ? `<a href="/app/sales-order/${encodeURIComponent(l.sales_order)}">${esc(l.sales_order)}</a>`
                    : '<span class="text-muted">—</span>'}</td>
                <td>${esc(l.status || "")}</td>
                <td>${esc(l.current_stage || "")}</td>
                <td>${fmt(l.total_yarn_received_kg)}</td>
                <td>${fmt(l.yarn_in_process_kg)}</td>
                <td>${fmt(l.weaved_pcs_received)}</td>
                <td>${fmt(l.finished_goods_qty)}</td>
                <td>${fmt(l.dispatched_qty)}</td>
                <td>${l.batch_count || 0}</td></tr>`;
        });
        html += "</tbody></table></div>";
        $body.html(html);
    }

    load();
};
