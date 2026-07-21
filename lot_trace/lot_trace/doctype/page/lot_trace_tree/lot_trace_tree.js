// V7 — Lot Trace Tree: yarn -> batches per stage -> documents.
// Data: lot_trace.api.tree.get_trace_tree

frappe.pages["lot-trace-tree"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper, title: __("Lot Trace Tree"), single_column: true,
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

    const $body = $('<div style="padding:10px 0">').appendTo(page.main);
    const esc = frappe.utils.escape_html;
    const fmt = (v) => frappe.format(v || 0, { fieldtype: "Float" });

    function load() {
        if (!filters.root_lot && !filters.product && !filters.sales_order) {
            $body.html(`<div class="text-muted text-center" style="padding:60px">
                ${__("Select a Root Lot (or filter by Sales Order / Product) to render its trace tree")}</div>`);
            return;
        }
        frappe.call({
            method: "lot_trace.api.tree.get_trace_tree",
            args: filters,
            callback: (r) => render((r.message || {}).lots || []),
        });
    }

    function render(lots) {
        if (!lots.length) {
            $body.html(`<div class="text-muted text-center" style="padding:60px">
                ${__("No lots match these filters")}</div>`);
            return;
        }
        let html = "";
        lots.forEach((lot) => {
            html += `<div style="border:1px solid var(--border-color);border-radius:8px;
                padding:14px;margin-bottom:14px">
                <h5 style="margin:0 0 4px">
                  <a href="/app/root-lot/${encodeURIComponent(lot.name)}">
                  ${esc(lot.lot_code || lot.name)}</a>
                  <span class="indicator-pill ${lot.status === "Open" ? "orange" : "green"}"
                    style="margin-left:8px">${esc(lot.status || "")}</span></h5>
                <div class="text-muted" style="margin-bottom:8px">
                  ${__("Product")}: ${esc(lot.product || "")} ·
                  ${__("Stage")}: ${esc(lot.current_stage || "")} ·
                  ${__("Yarn received")}: ${fmt(lot.total_yarn_received_kg)} Kg</div>`;

            html += `<div style="margin-left:12px">
                <b>${__("Yarn Receipts")}</b><ul style="margin:4px 0 10px">`;
            (lot.receipts || []).forEach((rc) => {
                html += `<li>${esc(rc.yarn_item)} (${esc(rc.item_abbr || "")}) →
                    <a href="/app/batch/${encodeURIComponent(rc.nt_batch || "")}">
                    ${esc(rc.nt_batch || "")}</a> · ${fmt(rc.received_kg)} Kg ·
                    <a href="/app/${frappe.router.slug(rc.source_doctype || "")}/${encodeURIComponent(rc.source_doc || "")}">
                    ${esc(rc.source_doc || "")}</a></li>`;
            });
            if (!(lot.receipts || []).length)
                html += `<li class="text-muted">${__("No receipts yet")}</li>`;
            html += "</ul>";

            (lot.stages || []).forEach((st) => {
                html += `<b>${esc(st.label)} (${esc(st.stage)})</b>
                    <ul style="margin:4px 0 10px">`;
                (st.batches || []).forEach((b) => {
                    html += `<li><a href="/app/batch/${encodeURIComponent(b.batch)}">
                        ${esc(b.batch)}</a> · ${esc(b.item || "")} ·
                        ${__("balance")} ${fmt(b.qty)}`;
                    if ((b.documents || []).length) {
                        html += `<ul>`;
                        b.documents.forEach((d) => {
                            html += `<li><a href="/app/${frappe.router.slug(d.voucher_type)}/${encodeURIComponent(d.voucher_no)}">
                                ${esc(d.voucher_type)}: ${esc(d.voucher_no)}</a></li>`;
                        });
                        html += `</ul>`;
                    }
                    html += `</li>`;
                });
                html += "</ul>";
            });
            html += "</div></div>";
        });
        $body.html(html);
    }

    load();
};
