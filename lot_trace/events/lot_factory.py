# -*- coding: utf-8 -*-
# Lot creation + THE totals engine (design P2): every Root Lot quantity is
# derived from the Lot Receipts child table + live Stock Ledger balances by
# apply_derived(). No scattered incremental writes anywhere in the app.

import frappe
from frappe.utils import flt, getdate

from lot_trace.events import common

EPS = 1e-6

YARN_STAGES = ("NT", "DY")
DISPATCH_STAGES = ("FG", "CT")


# ---------------------------------------------------------------- creation

def create_root_lot(rule, posting_date=None, sales_order=None):
    """New Root Lot for a naming rule: {prefix}/{MMYY}/{serial:02d}."""
    d = getdate(posting_date or frappe.utils.today())
    period = f"{d.month:02d}{str(d.year)[2:]}"
    serial = _next_serial(rule.name, period)
    lot_code = f"{rule.lot_code_prefix}/{period}/{serial:02d}"

    doc = frappe.get_doc({
        "doctype": "Root Lot",
        "lot_code": lot_code,
        "naming_rule": rule.name,
        "product": rule.product,
        "route": rule.get("route"),
        "serial": serial,
        "period": period,
        "sales_order": sales_order,
        "status": "Open",
        "current_stage": common.first_stage_for_rule(rule),
    })
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def _next_serial(rule_name, period):
    row = frappe.db.sql(
        "SELECT MAX(serial) FROM `tabRoot Lot` "
        "WHERE naming_rule = %s AND period = %s", (rule_name, period))
    return int(row[0][0] or 0) + 1


# ---------------------------------------------------------------- receipts

def record_lot_receipt(root_lot, yarn_item, item_abbr, batch_no, received_kg,
                       source_doctype, source_doc, supplier=None):
    lot = frappe.get_doc("Root Lot", root_lot)
    lot.append("lot_receipts", {
        "yarn_item": yarn_item,
        "item_abbr": item_abbr,
        "supplier": supplier,
        "nt_batch": batch_no,
        "received_kg": flt(received_kg),
        "source_doctype": source_doctype,
        "source_doc": source_doc,
    })
    lot.flags.ignore_permissions = True
    lot.save()  # validate -> apply_derived


def remove_lot_receipts_for_source(source_doctype, source_doc):
    """On source cancel: drop its receipt rows and refresh totals."""
    parents = {r.parent for r in frappe.get_all(
        "Lot Receipt",
        filters={"source_doctype": source_doctype, "source_doc": source_doc,
                 "parenttype": "Root Lot"},
        fields=["parent"])}
    for name in parents:
        lot = frappe.get_doc("Root Lot", name)
        lot.lot_receipts = [
            r for r in lot.lot_receipts
            if not (r.source_doctype == source_doctype
                    and r.source_doc == source_doc)]
        lot.flags.ignore_permissions = True
        lot.save()


# ------------------------------------------------------------ totals engine

def apply_derived(lot):
    """Set every derived quantity on a Root Lot document (in memory).
    Called from RootLot.validate on every save."""
    lot.received_qty = sum(
        flt(r.received_kg) for r in (lot.get("lot_receipts") or []))

    rule_yarns = set(frappe.get_all(
        "Lot Naming Rule Yarn",
        filters={"parent": lot.naming_rule, "parenttype": "Lot Naming Rule"},
        pluck="yarn_item")) if lot.naming_rule else set()
    received = {r.yarn_item for r in (lot.get("lot_receipts") or [])}
    lot.intake_complete = 1 if rule_yarns and rule_yarns <= received else 0

    lot.yarn_in_process_qty = _stage_balance(lot.name, YARN_STAGES)
    lot.weaved_pcs = _stage_inflow(lot.name, ("WV",))

    fg_in = _stage_inflow(lot.name, ("FG",))
    lot.fg_qty = fg_in if fg_in > EPS else _stage_inflow(lot.name, ("CT",))

    lot.dispatched_qty = _dispatched_qty(lot.name)

    # status: Completed only when the FG chain is closed
    if lot.status != "Short Closed":
        if flt(lot.fg_qty) > EPS and \
                flt(lot.dispatched_qty) >= flt(lot.fg_qty) - EPS:
            lot.status = "Completed"
        elif lot.status == "Completed":
            lot.status = "In Process"


def recompute_totals(root_lot):
    """Recompute + persist totals for one lot (called by event handlers
    after stock documents post/cancel)."""
    if not root_lot or not frappe.db.exists("Root Lot", root_lot):
        return
    lot = frappe.get_doc("Root Lot", root_lot)
    apply_derived(lot)
    frappe.db.set_value("Root Lot", root_lot, {
        "received_qty": lot.received_qty,
        "intake_complete": lot.intake_complete,
        "yarn_in_process_qty": lot.yarn_in_process_qty,
        "weaved_pcs": lot.weaved_pcs,
        "fg_qty": lot.fg_qty,
        "dispatched_qty": lot.dispatched_qty,
        "status": lot.status,
    }, update_modified=False)


def recompute_for_batches(batch_list):
    """Recompute every lot touched by the given batch numbers."""
    lots = {common.get_root_lot_of_batch(b) for b in batch_list if b}
    for lot in filter(None, lots):
        recompute_totals(lot)


# ------------------------------------------------------------- SLE reading
# Read-only Stock Ledger sums — never touches core stock logic (design P5).

def _lot_batches(root_lot, stages):
    return frappe.get_all(
        "Batch",
        filters={"root_lot": root_lot, "process_stage": ["in", list(stages)]},
        pluck="name")


def _stage_balance(root_lot, stages):
    batches = _lot_batches(root_lot, stages)
    if not batches:
        return 0.0
    row = frappe.db.sql(
        "SELECT SUM(actual_qty) FROM `tabStock Ledger Entry` "
        "WHERE batch_no IN %(b)s AND is_cancelled = 0",
        {"b": tuple(batches)})
    return flt(row[0][0])


def _stage_inflow(root_lot, stages):
    batches = _lot_batches(root_lot, stages)
    if not batches:
        return 0.0
    row = frappe.db.sql(
        "SELECT SUM(actual_qty) FROM `tabStock Ledger Entry` "
        "WHERE batch_no IN %(b)s AND is_cancelled = 0 AND actual_qty > 0",
        {"b": tuple(batches)})
    return flt(row[0][0])


def _dispatched_qty(root_lot):
    """Net qty of FG/CT batches shipped via FINAL dispatches (DN, or SI with
    update_stock). Derived from SLE so returns/cancellations self-correct."""
    batches = _lot_batches(root_lot, DISPATCH_STAGES)
    if not batches:
        return 0.0
    total = 0.0
    row = frappe.db.sql("""
        SELECT COALESCE(SUM(-sle.actual_qty), 0)
        FROM `tabStock Ledger Entry` sle
        JOIN `tabDelivery Note` dn ON sle.voucher_type = 'Delivery Note'
             AND sle.voucher_no = dn.name
        WHERE sle.batch_no IN %(b)s AND sle.is_cancelled = 0
          AND dn.docstatus = 1 AND dn.dispatch_type = 'Final'
    """, {"b": tuple(batches)})
    total += flt(row[0][0])
    row = frappe.db.sql("""
        SELECT COALESCE(SUM(-sle.actual_qty), 0)
        FROM `tabStock Ledger Entry` sle
        JOIN `tabSales Invoice` si ON sle.voucher_type = 'Sales Invoice'
             AND sle.voucher_no = si.name
        WHERE sle.batch_no IN %(b)s AND sle.is_cancelled = 0
          AND si.docstatus = 1 AND si.update_stock = 1
          AND si.dispatch_type = 'Final'
    """, {"b": tuple(batches)})
    total += flt(row[0][0])
    return max(total, 0.0)
