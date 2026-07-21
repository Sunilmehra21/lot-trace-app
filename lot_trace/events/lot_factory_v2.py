# -*- coding: utf-8 -*-
# V7 — Lot / batch creation and totals. THE fix for "root lot qty shows 0":
# the Lot Receipts child table is the single source of truth, and
# recompute_totals() derives every header number from it + batch stock.

from datetime import datetime

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2


# ---------------------------------------------------------------- creation

def create_root_lot(rule, sales_order=None):
    period = datetime.now().strftime("%m%y")
    serial = _next_serial(rule.name, period)
    lot_code = f"{rule.lot_code_prefix}/{period}/{serial:02d}"
    doc = frappe.get_doc({
        "doctype": "Root Lot",
        "lot_code": lot_code,
        "serial": serial,
        "period": period,
        "product": rule.product,
        "naming_rule": rule.name,
        "sales_order": sales_order,
        "status": "Open",
        "current_stage": "NT",
    })
    doc.insert(ignore_permissions=True)
    return doc.name


def _next_serial(rule_name, period):
    row = frappe.db.sql(
        "select max(serial) from `tabRoot Lot` "
        "where naming_rule=%s and period=%s", (rule_name, period))
    return int(row[0][0] or 0) + 1


def ensure_batch(batch_name, item_code, root_lot, stage):
    if frappe.db.exists("Batch", batch_name):
        frappe.db.set_value("Batch", batch_name, {
            "custom_root_lot": root_lot, "custom_stage": stage,
        }, update_modified=False)
        return batch_name
    b = frappe.get_doc({
        "doctype": "Batch",
        "batch_id": batch_name,
        "item": item_code,
        "custom_root_lot": root_lot,
        "custom_stage": stage,
    })
    b.insert(ignore_permissions=True)
    return b.name


# ---------------------------------------------------------------- receipts

def record_lot_receipt(root_lot, yarn_item, item_abbr, nt_batch, received_kg,
                       source_doctype, source_doc):
    lot = frappe.get_doc("Root Lot", root_lot)
    lot.append("lot_receipts", {
        "yarn_item": yarn_item,
        "item_abbr": item_abbr,
        "nt_batch": nt_batch,
        "received_kg": flt(received_kg),
        "source_doctype": source_doctype,
        "source_doc": source_doc,
    })
    _apply_derived(lot)
    lot.flags.ignore_permissions = True
    lot.save()


def remove_lot_receipts_for_source(source_doctype, source_doc):
    """On source cancel: drop its receipt rows, reopen intake, fix totals."""
    parents = {r.parent for r in frappe.get_all(
        "Lot Receipt",
        filters={"source_doctype": source_doctype, "source_doc": source_doc},
        fields=["parent"])}
    for name in parents:
        lot = frappe.get_doc("Root Lot", name)
        lot.lot_receipts = [
            r for r in lot.lot_receipts
            if not (r.source_doctype == source_doctype
                    and r.source_doc == source_doc)]
        _apply_derived(lot)
        lot.flags.ignore_permissions = True
        lot.save()


# ----------------------------------------------------------------- totals

def _apply_derived(lot):
    """Set every derived header value from the child table + batch stock."""
    lot.total_yarn_received_kg = sum(
        flt(r.received_kg) for r in lot.lot_receipts)

    rule_yarns = set(frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"parent": lot.naming_rule, "parenttype": "Lot Naming Rule"},
        pluck="yarn_item")) if lot.naming_rule else set()
    received = {r.yarn_item for r in lot.lot_receipts}
    lot.intake_complete = 1 if rule_yarns and rule_yarns <= received else 0

    lot.yarn_in_process_kg = stage_balance(lot.name, ["NT", "DY"])
    lot.weaved_pcs_received = stage_balance(lot.name, ["WV"])
    lot.finished_goods_qty = stage_balance(lot.name, ["CT"])
    lot.dispatched_qty = dispatched_qty(lot.name)


def recompute_totals(root_lot):
    """Recompute + persist totals for one lot (patch / dashboard refresh)."""
    lot = frappe.get_doc("Root Lot", root_lot)
    _apply_derived(lot)
    frappe.db.set_value("Root Lot", root_lot, {
        "total_yarn_received_kg": lot.total_yarn_received_kg,
        "intake_complete": lot.intake_complete,
        "yarn_in_process_kg": lot.yarn_in_process_kg,
        "weaved_pcs_received": lot.weaved_pcs_received,
        "finished_goods_qty": lot.finished_goods_qty,
        "dispatched_qty": lot.dispatched_qty,
    }, update_modified=False)


def stage_balance(root_lot, stages):
    """Current stock balance across all batches of the lot at given stages.
    Read-only SLE sum — never touches core stock logic."""
    batches = frappe.get_all(
        "Batch",
        filters={"custom_root_lot": root_lot,
                 "custom_stage": ["in", stages]},
        pluck="name")
    if not batches:
        return 0.0
    row = frappe.db.sql(
        "select sum(actual_qty) from `tabStock Ledger Entry` "
        "where batch_no in %(b)s and is_cancelled=0", {"b": tuple(batches)})
    return flt(row[0][0])


def dispatched_qty(root_lot):
    """Qty of this lot's batches shipped via submitted Delivery Notes."""
    batches = frappe.get_all(
        "Batch", filters={"custom_root_lot": root_lot}, pluck="name")
    if not batches:
        return 0.0
    row = frappe.db.sql(
        "select sum(dni.stock_qty) from `tabDelivery Note Item` dni "
        "join `tabDelivery Note` dn on dn.name = dni.parent "
        "where dn.docstatus = 1 and dni.batch_no in %(b)s",
        {"b": tuple(batches)})
    return flt(row[0][0])


def set_current_stage(root_lot, stage):
    frappe.db.set_value("Root Lot", root_lot, "current_stage", stage,
                        update_modified=False)
