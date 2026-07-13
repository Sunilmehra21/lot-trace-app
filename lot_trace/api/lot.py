# Whitelisted lot APIs: full trace, product re-assignment (audited),
# at-weaver balance (BOM-based conversion, as confirmed).

import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_lot_trace(root_lot):
    """Every stock movement of every stage batch under a root lot, in time order."""
    frappe.has_permission("Root Lot", "read", throw=True)
    return frappe.db.sql(
        """
        SELECT sle.posting_date, sle.posting_time, b.process_stage AS stage,
               sle.batch_no, sle.item_code, sle.warehouse,
               sle.voucher_type, sle.voucher_no,
               sle.actual_qty, sle.qty_after_transaction, sle.stock_uom
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE b.root_lot = %s AND sle.is_cancelled = 0
        ORDER BY sle.posting_date, sle.posting_time, sle.creation
        """,
        root_lot, as_dict=True)


@frappe.whitelist()
def reassign_lot(root_lot, new_product, reason):
    """Divert a lot to the other product - Lot Manager only, fully audited."""
    if "Lot Manager" not in frappe.get_roles() and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only Lot Manager can re-assign a lot."), frappe.PermissionError)
    if not reason:
        frappe.throw(_("A reason is mandatory for lot re-assignment."))

    lot = frappe.get_doc("Root Lot", root_lot)
    old_product = lot.product
    lot.product = new_product
    lot.flags.ignore_permissions = True
    lot.save()  # track_changes keeps the version history

    lot.add_comment("Comment", _(
        "Lot re-assigned from product {0} to {1} by {2}. Reason: {3}"
    ).format(old_product, new_product, frappe.session.user, reason))

    from lot_trace.events.common import log_exception
    log_exception("Manual Override", "Info", root_lot=root_lot,
                  message=_("Re-assigned {0} -> {1}: {2}")
                  .format(old_product, new_product, reason))
    return lot.name


def yarn_per_unit_from_bom(weaved_item, dyed_yarn_item=None):
    """kg of dyed yarn per 1 unit of weaved pcs, from the item's default BOM."""
    bom = frappe.db.get_value(
        "BOM", {"item": weaved_item, "is_active": 1, "is_default": 1}, "name")
    if not bom:
        return 0
    filters = {"parent": bom}
    if dyed_yarn_item:
        filters["item_code"] = dyed_yarn_item
    rows = frappe.get_all("BOM Item", filters=filters,
                          fields=["item_code", "stock_qty"])
    bom_qty = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
    return sum(flt(r.stock_qty) for r in rows) / bom_qty


@frappe.whitelist()
def at_weaver_balance(weaver=None, root_lot=None):
    """Dyed yarn lying at weavers, per lot:
    sold(-DY out via DN/SI) - consumed(weaved pcs received x BOM yarn-per-unit)."""
    frappe.has_permission("Root Lot", "read", throw=True)

    cond, vals = "", {"stage": "DY"}
    if root_lot:
        cond += " AND b.root_lot = %(root_lot)s"
        vals["root_lot"] = root_lot

    sold = frappe.db.sql(
        """
        SELECT b.root_lot, SUM(-sle.actual_qty) AS sold_qty
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE b.process_stage = %(stage)s AND sle.is_cancelled = 0
          AND sle.actual_qty < 0
          AND sle.voucher_type IN ('Delivery Note', 'Sales Invoice') {cond}
        GROUP BY b.root_lot
        """.format(cond=cond), vals, as_dict=True)

    result = []
    for s in sold:
        pr_rows = frappe.db.sql(
            """
            SELECT pri.item_code, SUM(pri.stock_qty) AS qty, pr.supplier
            FROM `tabPurchase Receipt Item` pri
            JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pri.root_lot = %s AND pr.docstatus = 1 AND pr.is_return = 0
            GROUP BY pri.item_code, pr.supplier
            """, s.root_lot, as_dict=True)
        consumed = sum(
            flt(r.qty) * yarn_per_unit_from_bom(r.item_code) for r in pr_rows)
        supplier = pr_rows[0].supplier if pr_rows else None
        if weaver and supplier and weaver != supplier:
            continue
        result.append({
            "root_lot": s.root_lot,
            "weaver": supplier,
            "dyed_yarn_sold_kg": flt(s.sold_qty),
            "consumed_equiv_kg": round(consumed, 2),
            "balance_at_weaver_kg": round(flt(s.sold_qty) - consumed, 2),
        })
    return result
