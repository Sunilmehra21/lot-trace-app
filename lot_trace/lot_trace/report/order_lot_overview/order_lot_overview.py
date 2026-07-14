import frappe
from frappe import _
from frappe.utils import flt

# Stages carried in yarn (kg). Everything from weaving onward is in pcs (Nos)
# and must NOT be summed into the yarn In-Process figure.
YARN_STAGES = {"NT", "DY"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    lot_filters = {}
    if filters.sales_order:
        lot_filters["sales_order"] = filters.sales_order
    if filters.product:
        lot_filters["product"] = filters.product
    if filters.status:
        lot_filters["status"] = filters.status

    lots = frappe.get_all(
        "Root Lot", filters=lot_filters,
        fields=["name", "product", "supplier", "received_qty", "uom",
                "current_stage", "fg_qty", "dispatched_qty", "status"],
        order_by="name")

    data = []
    for lot in lots:
        stage_qty = get_stage_balances(lot.name)
        dy_stage = stage_qty.get("DY", {})
        dy_in = dy_stage.get("in_qty", 0)  # what was sent to dyer
        dy_out = dy_stage.get("out_qty", 0)  # what came back

        data.append({
            "root_lot": lot.name,
            "product": lot.product,
            "supplier": lot.supplier,
            "received_qty": lot.received_qty,
            "dyed_qty": dy_out,
            "dye_loss_pct": loss_pct_for_stage(dy_in, dy_out),
            "weaved_qty": stage_qty.get("WV", {}).get("in_qty", 0),
            # In-Process = yarn (kg) still in the pipeline, yarn stages only.
            # Weaved pcs stages are a different UOM (Nos) and are excluded.
            "in_process_qty": sum(
                v.get("balance", 0)
                for k, v in stage_qty.items()
                if k in YARN_STAGES),
            "fg_qty": lot.fg_qty,
            "dispatched_qty": lot.dispatched_qty,
            "current_stage": lot.current_stage,
            "status": lot.status,
            "open_exceptions": frappe.db.count(
                "Lot Exception", {"root_lot": lot.name, "resolved": 0}),
        })

    columns = [
        {"label": _("Root Lot"), "fieldname": "root_lot", "fieldtype": "Link",
         "options": "Root Lot", "width": 150},
        {"label": _("Product"), "fieldname": "product", "fieldtype": "Link",
         "options": "Item", "width": 160},
        {"label": _("Yarn Supplier"), "fieldname": "supplier", "fieldtype": "Link",
         "options": "Supplier", "width": 130},
        {"label": _("Yarn Recd (Kg)"), "fieldname": "received_qty",
         "fieldtype": "Float", "width": 105},
        {"label": _("Dyed (Kg)"), "fieldname": "dyed_qty", "fieldtype": "Float",
         "width": 90},
        {"label": _("Dye Loss %"), "fieldname": "dye_loss_pct", "fieldtype": "Percent",
         "width": 90},
        {"label": _("Weaved Pcs"), "fieldname": "weaved_qty", "fieldtype": "Float",
         "width": 95},
        {"label": _("In-Process (Kg)"), "fieldname": "in_process_qty",
         "fieldtype": "Float", "width": 110},
        {"label": _("FG Qty"), "fieldname": "fg_qty", "fieldtype": "Float", "width": 85},
        {"label": _("Dispatched"), "fieldname": "dispatched_qty", "fieldtype": "Float",
         "width": 95},
        {"label": _("Stage"), "fieldname": "current_stage", "fieldtype": "Link",
         "options": "Lot Process Stage", "width": 70},
        {"label": _("Status"), "fieldname": "status", "width": 100},
        {"label": _("Open Exc."), "fieldname": "open_exceptions", "fieldtype": "Int",
         "width": 80},
    ]
    return columns, data


def get_stage_balances(root_lot):
    """Get input/output/balance per stage using Stock Ledger Entries."""
    rows = frappe.db.sql(
        """
        SELECT b.process_stage AS stage,
               SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) AS in_qty,
               SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) AS out_qty,
               SUM(sle.actual_qty) AS balance
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE b.root_lot = %s AND sle.is_cancelled = 0
        GROUP BY b.process_stage
        """, root_lot, as_dict=True)
    return {r.stage: {
        "in_qty": flt(r.in_qty),
        "out_qty": flt(r.out_qty),
        "balance": flt(r.balance)
    } for r in rows}


def loss_pct_for_stage(in_qty, out_qty):
    """Loss % = (sent - received) / sent * 100."""
    if not flt(in_qty) or not flt(out_qty):
        return 0
    # loss % based on what was sent, not total purchase
    return round((flt(in_qty) - flt(out_qty)) / flt(in_qty) * 100, 2)
