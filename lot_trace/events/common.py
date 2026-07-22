# -*- coding: utf-8 -*-
# Shared helpers: settings, routes, colour, stage-batch factory,
# single-lot guard, exceptions, BOM helpers, loss check.
# Field names are PLAIN (Batch.root_lot / Batch.process_stage) — design P1.

import frappe
from frappe import _
from frappe.utils import flt

EPS = 1e-6


def get_settings():
    return frappe.get_cached_doc("Lot Trace Settings")


# ----------------------------------------------------------------- routes

def get_route_stages(root_lot):
    """Ordered stage list of the lot's route, or None (= global sequence)."""
    route = frappe.db.get_value("Root Lot", root_lot, "route")
    if not route:
        return None
    stages = frappe.get_all(
        "Lot Route Stage", filters={"parent": route},
        order_by="idx asc", pluck="stage")
    return stages or None


def first_stage_for_rule(rule):
    """Birth stage of a rule's route (fabric-first support). Default NT."""
    route = rule.get("route")
    if route:
        stages = frappe.get_all(
            "Lot Route Stage", filters={"parent": route},
            order_by="idx asc", pluck="stage")
        if stages:
            return stages[0]
    return "NT"


def stage_order_index(root_lot, stage_code):
    stages = get_route_stages(root_lot)
    if stages and stage_code in stages:
        return stages.index(stage_code)
    return frappe.db.get_value("Lot Process Stage", stage_code, "sequence") or 0


def next_stage_after(stage_code, root_lot=None):
    if root_lot:
        stages = get_route_stages(root_lot)
        if stages and stage_code in stages:
            i = stages.index(stage_code)
            return stages[i + 1] if i + 1 < len(stages) else None
    seq = frappe.db.get_value("Lot Process Stage", stage_code, "sequence") or 0
    nxt = frappe.get_all("Lot Process Stage",
                         filters={"sequence": [">", seq], "active": 1},
                         order_by="sequence asc", limit=1, pluck="name")
    return nxt[0] if nxt else None


# ----------------------------------------------------------------- colour

def color_abbr_for_item(item_code):
    """Colour abbreviation for DY batch names ('BK' for Black...)."""
    if not item_code:
        return None
    attr_value = frappe.db.get_value(
        "Item Variant Attribute",
        {"parent": item_code, "attribute": "Colour"},
        "attribute_value")
    if not attr_value:
        attr_value = frappe.db.get_value(
            "Item Variant Attribute",
            {"parent": item_code, "attribute": "Color"},
            "attribute_value")
    if attr_value:
        for attribute in ("Colour", "Color"):
            abbr = frappe.db.get_value(
                "Item Attribute Value",
                {"parent": attribute, "attribute_value": attr_value},
                "abbr")
            if abbr:
                return abbr.upper()[:4]
        return attr_value.replace(" ", "")[:4].upper()

    parts = item_code.upper().replace("_", "-").split("-")
    known_non_color = {"CN", "EU", "US", "NT", "DY", "WV", "CT", "FG",
                       "MA", "RM", "YN", "FA", "BCI", "MAV"}
    for p in reversed(parts):
        if p and 2 <= len(p) <= 4 and p.isalpha() and p not in known_non_color:
            return p
    return None


# ------------------------------------------------------ stage batch factory

def batch_id_for_stage(root_lot, stage_code, item_code, item_abbr=None):
    """Canonical batch id (design §4):
    NT  {lot}-{ABBR}-NT          e.g. MV/BA/0726/01-A-NT
    DY  {lot}-{ABBR}-{COLOR}-DY  e.g. MV/BA/0726/01-A-BK-DY
    WV/CT/FG/...  {lot}-{suffix} e.g. MV/BA/0726/01-WV
    Abbr and colour segments are skipped when unknown."""
    try:
        stage = frappe.get_cached_doc("Lot Process Stage", stage_code)
        suffix = stage.batch_suffix or stage_code
    except Exception:
        suffix = stage_code

    abbr = (item_abbr or "").strip().upper()
    if stage_code == "NT":
        return f"{root_lot}-{abbr}-NT" if abbr else f"{root_lot}-NT"
    if stage_code == "DY":
        color = color_abbr_for_item(item_code)
        mid = "-".join(x for x in (abbr, color) if x)
        return f"{root_lot}-{mid}-DY" if mid else f"{root_lot}-DY"
    return f"{root_lot}-{suffix}"


def create_stage_batch(root_lot, stage_code, item_code, item_abbr=None):
    """Get or create the batch for (root_lot, stage, item); advance the
    lot's current stage forward (route-aware)."""
    if not frappe.db.exists("Lot Process Stage", stage_code):
        frappe.throw(_("Lot Process Stage {0} not found").format(stage_code))

    route_stages = get_route_stages(root_lot)
    if route_stages and stage_code not in route_stages:
        frappe.throw(_(
            "Stage {0} is not part of the route of lot {1} ({2}). "
            "Check the Lot Route or the document's stage."
        ).format(stage_code, root_lot, " → ".join(route_stages)))

    batch_id = batch_id_for_stage(root_lot, stage_code, item_code, item_abbr)

    if frappe.db.exists("Batch", batch_id):
        frappe.db.set_value("Batch", batch_id, {
            "root_lot": root_lot, "process_stage": stage_code,
        }, update_modified=False)
    else:
        batch = frappe.new_doc("Batch")
        batch.batch_id = batch_id
        batch.item = item_code
        batch.root_lot = root_lot
        batch.process_stage = stage_code
        batch.flags.ignore_permissions = True
        batch.insert()

    cur = frappe.db.get_value("Root Lot", root_lot, "current_stage")
    cur_idx = stage_order_index(root_lot, cur) if cur else -1
    new_idx = stage_order_index(root_lot, stage_code)
    if new_idx >= cur_idx:
        frappe.db.set_value(
            "Root Lot", root_lot,
            {"current_stage": stage_code, "status": "In Process"},
            update_modified=False)
    return batch_id


def get_root_lot_of_batch(batch_no):
    if not batch_no:
        return None
    return frappe.db.get_value("Batch", batch_no, "root_lot")


# ------------------------------------------------- single-lot-per-doc guard

def collect_root_lots(doc, batch_field="batch_no", tables=("items",)):
    lots = set()
    for table in tables:
        for row in doc.get(table) or []:
            rl = get_root_lot_of_batch(row.get(batch_field))
            if rl:
                lots.add(rl)
    return lots


def enforce_single_lot(doc, lots):
    """Mixing policy Block / Warn / Allow (Lot Trace Settings)."""
    if len(lots) <= 1:
        return
    policy = get_settings().mixing_policy or "Block"
    if policy == "Allow":
        return
    allow_override = bool(doc.get("allow_mixed_lots"))
    if policy == "Block" and not allow_override:
        frappe.throw(_(
            "Lot mixing not allowed: this document touches {0} root lots "
            "({1}). Split into one document per lot, or a Lot Manager can "
            "tick 'Allow Mixed Lots' (logged)."
        ).format(len(lots), ", ".join(sorted(lots))))
    if allow_override and "Lot Manager" not in frappe.get_roles() \
            and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only a Lot Manager may use 'Allow Mixed Lots'."))
    log_exception(
        "Mixed Lots Override" if allow_override else "Mixed Lots Warning",
        "Warning",
        erp_doc_type=doc.doctype, erp_doc_name=doc.name,
        message=_("Document touches root lots: {0}").format(
            ", ".join(sorted(lots))))


# -------------------------------------------------------------- exceptions

def log_exception(exception_type, severity, message="", root_lot=None,
                  erp_doc_type=None, erp_doc_name=None):
    try:
        te = frappe.new_doc("Lot Exception")
        te.update({
            "exception_type": exception_type, "severity": severity,
            "message": message, "root_lot": root_lot,
            "erp_doc_type": erp_doc_type, "erp_doc_name": erp_doc_name,
        })
        te.flags.ignore_permissions = True
        te.insert()
    except Exception:
        frappe.log_error(title="Lot Exception insert failed",
                         message=frappe.get_traceback())


# ------------------------------------------------------------ BOM helpers

def get_bom_for_item(item_code):
    """Default active BOM -> any active -> any submitted."""
    return (frappe.db.get_value("BOM", {"item": item_code, "is_active": 1,
                                        "is_default": 1}, "name")
            or frappe.db.get_value("BOM", {"item": item_code,
                                           "is_active": 1}, "name")
            or frappe.db.get_value("BOM", {"item": item_code,
                                           "docstatus": 1}, "name"))


def yarn_per_unit_from_bom(output_item, input_item=None):
    """Input qty consumed per 1 unit of output, from the output's BOM."""
    if not output_item:
        return 0
    bom = get_bom_for_item(output_item)
    if not bom:
        return 0
    filters = {"parent": bom}
    if input_item:
        filters["item_code"] = input_item
    rows = frappe.get_all("BOM Item", filters=filters, fields=["stock_qty"])
    if not rows:
        return 0
    bom_qty = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
    return sum(flt(r.stock_qty) for r in rows) / bom_qty


def expected_input_per_unit(output_item):
    return yarn_per_unit_from_bom(output_item)


# -------------------------------------------------------------- loss check

def check_stage_loss(root_lot, stage_code, input_qty, output_qty,
                     erp_doc_type=None, erp_doc_name=None, output_item=None):
    """Log a Lot Exception when the stage loss exceeds tolerance.
    Never blocks stock posting."""
    input_qty, output_qty = flt(input_qty), flt(output_qty)
    if not input_qty or not output_qty:
        return
    actual_loss = input_qty - output_qty
    per_unit = expected_input_per_unit(output_item) if output_item else 0
    if per_unit > 0:
        expected_input = output_qty * per_unit
        expected_loss = expected_input - output_qty
        if input_qty > expected_input + 0.1:
            log_exception(
                "Loss Out of Tolerance", "Warning", root_lot=root_lot,
                erp_doc_type=erp_doc_type, erp_doc_name=erp_doc_name,
                message=_(
                    "Stage {0}: actual loss {1} exceeds BOM-expected loss {2} "
                    "(consumed {3}, received {4}, BOM allows {5})"
                ).format(stage_code, round(actual_loss, 2),
                         round(expected_loss, 2), input_qty, output_qty,
                         round(expected_input, 2)))
        return
    tol = flt(frappe.db.get_value(
        "Lot Process Stage", stage_code, "expected_loss_pct"))
    if tol <= 0:
        return
    loss_pct = actual_loss / input_qty * 100
    if loss_pct > tol + 0.01:
        log_exception(
            "Loss Out of Tolerance", "Warning", root_lot=root_lot,
            erp_doc_type=erp_doc_type, erp_doc_name=erp_doc_name,
            message=_(
                "Stage {0}: loss {1}% ({2}) exceeds tolerance {3}% "
                "(in {4}, out {5})"
            ).format(stage_code, round(loss_pct, 2), round(actual_loss, 2),
                     tol, input_qty, output_qty))
