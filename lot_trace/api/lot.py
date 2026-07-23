# -*- coding: utf-8 -*-
# Whitelisted lot APIs: full trace, product re-assignment (audited),
# at-weaver balance (BOM-based yarn conversion), weaver-aware link queries,
# per-item dyed availability, BOM-based weaving allocation,
# effective lot status, and lot birth from existing stock.

import frappe
from frappe import _
from frappe.utils import flt, getdate

from lot_trace.events import common

EPS = 1e-6


@frappe.whitelist()
def get_lot_trace(root_lot):
    """Full Stock Ledger Entry trace for all batches of a root lot."""
    frappe.has_permission("Root Lot", "read", throw=True)
    if not root_lot:
        return []
    batches = frappe.db.sql("""
        SELECT name, process_stage
        FROM `tabBatch`
        WHERE root_lot = %s
        ORDER BY process_stage
    """, root_lot, as_dict=True)
    if not batches:
        return []
    batch_names = [b.name for b in batches]
    return frappe.db.sql("""
        SELECT sle.*, b.process_stage, b.root_lot
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE sle.batch_no IN ({})
          AND sle.is_cancelled = 0
        ORDER BY sle.posting_date, sle.posting_time, sle.name
    """.format(",".join(["%s"] * len(batch_names))),
        batch_names, as_dict=True)


@frappe.whitelist()
def reassign_lot(root_lot, new_product, reason):
    """Divert a lot to another product — Lot Manager only, fully audited."""
    if "Lot Manager" not in frappe.get_roles() \
            and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only Lot Manager can re-assign a lot."),
                     frappe.PermissionError)
    if not reason:
        frappe.throw(_("Reason is required for lot re-assignment."))
    old_product = frappe.db.get_value("Root Lot", root_lot, "product")
    frappe.db.set_value("Root Lot", root_lot, "product", new_product,
                        update_modified=True)
    common.log_exception(
        "Manual Override", "Info", root_lot=root_lot,
        message=_("Product re-assigned from {0} to {1}. Reason: {2}"
                  ).format(old_product, new_product, reason))
    return {"root_lot": root_lot, "old_product": old_product,
            "new_product": new_product}


@frappe.whitelist()
def get_at_weaver_balance(root_lot=None, weaver=None):
    """At-weaver balance: dyed yarn sent to weaver minus BOM-consumed.
    Weaver can be a Customer with represents_supplier=1, or a Supplier name."""
    frappe.has_permission("Root Lot", "read", throw=True)
    filters = {}
    if root_lot:
        filters["root_lot"] = root_lot

    batches = frappe.get_all(
        "Batch",
        filters={**filters, "process_stage": "DY"},
        fields=["name", "root_lot", "item"])
    if not batches:
        return []

    # Map weaver (customer) to filter via represents_supplier if needed
    weaver_customers = None
    if weaver:
        weaver_customers = _customers_for_supplier(weaver)

    rows = []
    for b in batches:
        sent = _qty_sent_to_weaver(b.name, weaver_customers or weaver)
        consumed = _qty_consumed_from_batch(b.name)
        balance = flt(sent) - flt(consumed)
        if abs(balance) > EPS or sent > EPS:
            rows.append({
                "root_lot": b.root_lot,
                "batch": b.name,
                "item": b.item,
                "sent_to_weaver": round(sent, 3),
                "consumed_at_weaver": round(consumed, 3),
                "balance": round(balance, 3),
            })
    return rows


def _qty_sent_to_weaver(batch_no, weaver_customer=None):
    """Qty of this batch shipped via Delivery Note / Sales Invoice.
    weaver_customer can be a string or a list of customer names."""
    filters = "sle.batch_no = %s AND sle.is_cancelled = 0 AND sle.actual_qty < 0"
    params = [batch_no]

    if weaver_customer:
        if isinstance(weaver_customer, list):
            if not weaver_customer:
                return 0.0
            placeholders = ",".join(["%s"] * len(weaver_customer))
            dn_filter = f" AND dn.customer IN ({placeholders})"
            params.extend(weaver_customer)
        else:
            dn_filter = " AND dn.customer = %s"
            params.append(weaver_customer)
    else:
        dn_filter = ""

    row = frappe.db.sql("""
        SELECT COALESCE(SUM(-sle.actual_qty), 0)
        FROM `tabStock Ledger Entry` sle
        JOIN `tabDelivery Note` dn ON sle.voucher_type = 'Delivery Note'
             AND sle.voucher_no = dn.name
        WHERE {} {} AND dn.docstatus = 1
    """.format(filters, dn_filter), params)
    return flt(row[0][0])


def _qty_consumed_from_batch(batch_no):
    """Qty consumed in Subcontracting Receipts (supplied items)."""
    row = frappe.db.sql("""
        SELECT COALESCE(SUM(si.consumed_qty), 0)
        FROM `tabSubcontracting Receipt Supplied Item` si
        JOIN `tabSubcontracting Receipt` sr ON sr.name = si.parent
        WHERE si.batch_no = %s AND sr.docstatus = 1
    """, batch_no)
    return flt(row[0][0])


@frappe.whitelist()
def suggest_lot_consumption(purchase_receipt, item_code, qty_pcs):
    """BOM-based allocation of dyed yarn across open lots for a weaving PR.
    Returns a list of {root_lot, batch, qty_kg} rows."""
    frappe.has_permission("Purchase Receipt", "read", throw=True)
    qty_pcs = flt(qty_pcs)
    if not qty_pcs:
        return []

    yarn_per_pc = common.yarn_per_unit_from_bom(item_code)
    if not yarn_per_pc:
        return []
    total_yarn_needed = qty_pcs * yarn_per_pc

    available = get_at_weaver_balance()
    result, remaining = [], total_yarn_needed
    for row in available:
        if remaining <= EPS:
            break
        take = min(flt(row["balance"]), remaining)
        if take > EPS:
            result.append({
                "root_lot": row["root_lot"],
                "batch": row["batch"],
                "dyed_yarn_item": row["item"],
                "qty_kg": round(take, 3),
            })
            remaining -= take
    return result


@frappe.whitelist()
def get_effective_lot_status(root_lot):
    """Effective status considering remaining yarn in process."""
    frappe.has_permission("Root Lot", "read", throw=True)
    lot = frappe.get_doc("Root Lot", root_lot)
    from lot_trace.events.lot_factory import apply_derived
    apply_derived(lot)
    return {
        "status": lot.status,
        "received_qty": lot.received_qty,
        "yarn_in_process_qty": lot.yarn_in_process_qty,
        "weaved_pcs": lot.weaved_pcs,
        "fg_qty": lot.fg_qty,
        "dispatched_qty": lot.dispatched_qty,
        "intake_complete": lot.intake_complete,
    }


# ============================================================================
# Helper functions for customer/supplier mapping and filtering
# ============================================================================

def _customers_for_supplier(supplier_or_customer_name):
    """Map a supplier name to customer record(s) via represents_supplier field.
    Returns a list of customer names, or [supplier_or_customer_name] if no match."""
    if not supplier_or_customer_name:
        return []

    # Check if it's already a customer with represents_supplier
    cust = frappe.db.get_value(
        "Customer",
        supplier_or_customer_name,
        ["name", "represents_supplier"])
    if cust and cust[1]:  # represents_supplier = True
        return [supplier_or_customer_name]

    # Try to find customers that have this as represents_supplier
    customers = frappe.db.get_list(
        "Customer",
        filters={"represents_supplier": supplier_or_customer_name},
        pluck="name")

    if customers:
        return customers

    # Fallback: return the input as-is (might be a customer already)
    return [supplier_or_customer_name] if supplier_or_customer_name else []