import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.api.lot import get_lot_trace

# Stages, in flow order, used to lay out the overview columns.
GREIGE = "NT"
DYE = "DY"
WEAVE = "WV"
CUT = "CT"

# tolerance (kg) below which remaining dyed yarn is treated as fully consumed
CONSUMED_TOLERANCE_KG = 1.0


def execute(filters=None):
    filters = frappe._dict(filters or {})
    root_lots = get_root_lots(filters)

    columns = get_columns()
    data = []
    for lot in root_lots:
        row = build_row(lot)
        if row:
            data.append(row)
    return columns, data


def get_root_lots(filters):
    """Return the list of root lot ids to report on."""
    if filters.get("root_lot"):
        return [filters.root_lot]

    conditions = ["b.disabled = 0"]
    values = {}
    # A root lot is a Batch whose id has no stage suffix, i.e. it is the
    # greige/native batch that seeds the tree. We identify root lots as the
    # batches that carry a Sales Order / order reference custom field.
    order_field = frappe.db.has_column("Batch", "custom_sales_order")
    if filters.get("from_date"):
        conditions.append("b.creation >= %(from_date)s")
        values["from_date"] = filters.from_date
    if filters.get("to_date"):
        conditions.append("b.creation <= %(to_date)s")
        values["to_date"] = filters.to_date

    where = " AND ".join(conditions)
    if order_field:
        rows = frappe.db.sql(f"""
            SELECT b.name
            FROM `tabBatch` b
            WHERE {where} AND IFNULL(b.custom_sales_order, '') != ''
            ORDER BY b.creation DESC
        """, values, as_dict=True)
    else:
        # fallback: batches whose name does not contain a stage suffix
        rows = frappe.db.sql(f"""
            SELECT b.name
            FROM `tabBatch` b
            WHERE {where}
              AND b.name NOT LIKE '%%-DY%%'
              AND b.name NOT LIKE '%%-WV%%'
              AND b.name NOT LIKE '%%-CT%%'
            ORDER BY b.creation DESC
        """, values, as_dict=True)

    return [r.name for r in rows]


def build_row(root_lot):
    raw = get_lot_trace(root_lot)
    if not raw:
        return None

    stages = aggregate_stages(raw)

    greige_kg = flt(stages.get(GREIGE, {}).get("in_qty"))
    dyed_kg = flt(stages.get(DYE, {}).get("in_qty"))
    # B6 fix: weaved pieces = pieces RECEIVED from the weaver (netted in_qty),
    # not the current on-hand balance (which is 0 once sent to cutting).
    weaved_pcs = flt(stages.get(WEAVE, {}).get("in_qty"))
    cut_pcs = flt(stages.get(CUT, {}).get("in_qty"))

    status = effective_status(stages)

    return {
        "root_lot": root_lot,
        "greige_kg": greige_kg,
        "dyed_kg": dyed_kg,
        "weaved_pcs": weaved_pcs,
        "cut_pcs": cut_pcs,
        "dye_loss_kg": round(greige_kg - dyed_kg, 3) if greige_kg and dyed_kg else 0,
        "status": status,
    }


def aggregate_stages(raw):
    """Group SLEs by process stage; net inter-warehouse transfers so a stage's
    in_qty reflects what actually entered that stage (received), and balance is
    the current on-hand across all batches of that stage."""
    stages = {}
    for sle in raw:
        stage = sle.get("process_stage") or "?"
        qty = flt(sle.get("actual_qty"))
        s = stages.setdefault(stage, {"in_qty": 0.0, "out_qty": 0.0, "balance": 0.0})
        s["balance"] = round(s["balance"] + qty, 3)
        if qty > 0:
            s["in_qty"] = round(s["in_qty"] + qty, 3)
        else:
            s["out_qty"] = round(s["out_qty"] + abs(qty), 3)
    return stages


def effective_status(stages):
    """B6 fix: a lot is only Completed when its dyed yarn is effectively fully
    consumed (on-hand balance across dyed batches at/near zero). If dyed yarn
    still sits in stock or with a weaver, the lot is In Progress."""
    if not stages:
        return "Open"

    dye = stages.get(DYE)
    if not dye or not dye.get("in_qty"):
        # not yet dyed
        return "In Progress" if stages.get(GREIGE) else "Open"

    remaining_dyed = flt(dye.get("balance"))
    if remaining_dyed > CONSUMED_TOLERANCE_KG:
        return "In Progress"

    # dyed yarn consumed — check that downstream produced something
    if flt(stages.get(WEAVE, {}).get("in_qty")):
        return "Completed"
    return "In Progress"


def get_columns():
    return [
        {"label": _("Root Lot"), "fieldname": "root_lot", "fieldtype": "Link",
         "options": "Batch", "width": 200},
        {"label": _("Greige (Kg)"), "fieldname": "greige_kg", "fieldtype": "Float", "width": 110},
        {"label": _("Dyed (Kg)"), "fieldname": "dyed_kg", "fieldtype": "Float", "width": 110},
        {"label": _("Dye Loss (Kg)"), "fieldname": "dye_loss_kg", "fieldtype": "Float", "width": 110},
        {"label": _("Weaved (Pcs)"), "fieldname": "weaved_pcs", "fieldtype": "Float", "width": 110},
        {"label": _("Cut (Pcs)"), "fieldname": "cut_pcs", "fieldtype": "Float", "width": 110},
        {"label": _("Status"), "fieldname": "status", "width": 110},
    ]
