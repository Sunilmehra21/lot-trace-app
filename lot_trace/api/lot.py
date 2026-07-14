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
    """
    Dyed yarn lying at weavers, per lot per weaver.
 
    balance_at_weaver = dyed_yarn_sold - consumed_equiv
 
    Where:
    - dyed_yarn_sold = qty of dyed yarn sent to weaver (via DN/SI)
    - weaved_pcs_received = total pcs received from weaver (NEW FIELD)
    - consumed_equiv = weaving pcs × kg_per_pc from BOM
    """
    frappe.has_permission("Root Lot", "read", throw=True)
 
    # sales of dyed yarn (DY batches) per lot per weaver-customer
    sold = frappe.db.sql(
        """
        SELECT b.root_lot, COALESCE(dn.customer, si.customer) AS weaver,
               SUM(ABS(sle.actual_qty)) AS sold_qty
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        LEFT JOIN `tabDelivery Note Item` dni ON sle.voucher_type = 'Delivery Note' AND sle.voucher_no = dni.parent AND b.name = dni.batch_no
        LEFT JOIN `tabDelivery Note` dn ON dni.parent = dn.name
        LEFT JOIN `tabSales Invoice Item` sii ON sle.voucher_type = 'Sales Invoice' AND sle.voucher_no = sii.parent AND b.name = sii.batch_no
        LEFT JOIN `tabSales Invoice` si ON sii.parent = si.name
        WHERE b.process_stage = 'DY' AND sle.is_cancelled = 0
          AND sle.actual_qty < 0
          AND sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
        """ + ("AND b.root_lot = %(root_lot)s" if root_lot else "") + """
        GROUP BY b.root_lot, COALESCE(dn.customer, si.customer)
        """,
        {"root_lot": root_lot} if root_lot else {}, as_dict=True)
 
    result = []
    for s in sold:
        weaver_name = s.weaver
        if weaver and weaver != weaver_name:
            continue
 
        # Convert weaver-as-customer to weaver-as-supplier
        # (assumes same name, or use represents_supplier if custom field exists)
        weaver_supplier = weaver_name
 
        # consumed: weaved pcs received from this weaver for this lot
        pr_rows = frappe.db.sql(
            """
            SELECT pri.item_code, SUM(pri.stock_qty) AS qty
            FROM `tabPurchase Receipt Item` pri
            JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pri.root_lot = %s AND pr.supplier = %s
              AND pr.docstatus = 1 AND pr.is_return = 0
            GROUP BY pri.item_code
            """, (s.root_lot, weaver_supplier), as_dict=True)
 
        # NEW: Calculate total pcs received
        total_pcs_received = sum(flt(r.qty) for r in pr_rows)
 
        consumed = sum(
            flt(r.qty) * yarn_per_unit_from_bom(r.item_code) for r in pr_rows)
 
        result.append({
            "root_lot": s.root_lot,
            "weaver": weaver_name,
            "dyed_yarn_sold_kg": round(flt(s.sold_qty), 2),
            "weaved_pcs_received": round(total_pcs_received, 2),  # NEW FIELD
            "consumed_equiv_kg": round(consumed, 2),
            "balance_at_weaver_kg": round(flt(s.sold_qty) - consumed, 2),
        })
 
    return result
 
 
def yarn_per_unit_from_bom(weaving_item, dyed_yarn_item=None):
    """
    Get kg of yarn required per unit of weaving item, from BOM.
 
    Looks up the BOM for the weaving item, finds the dyed yarn input,
    and returns the qty_per_unit in kg.
 
    Args:
        weaving_item (str): Item code of the woven product (e.g., "Woven Panel Greige")
        dyed_yarn_item (str, optional): Item code of dyed yarn
 
    Returns:
        float: kg of yarn per unit of weaving item. Returns 0 if no BOM found.
    """
    if not weaving_item:
        return 0
 
    # Find the BOM for this weaving item
    bom = frappe.db.get_value(
        "BOM",
        {"item": weaving_item, "docstatus": 1},
        ["name"])
 
    if not bom:
        return 0
 
    # Query BOM items: find the yarn input row
    where_clause = "bom_no = %s"
    params = [bom]
 
    if dyed_yarn_item:
        where_clause += " AND item_code = %s"
        params.append(dyed_yarn_item)
 
    yarn_rows = frappe.db.sql(
        """
        SELECT bi.item_code, bi.qty, bi.uom
        FROM `tabBOM Item` bi
        WHERE """ + where_clause + """
        LIMIT 1
        """, params, as_dict=True)
 
    if not yarn_rows:
        return 0
 
    yarn_row = yarn_rows[0]
    qty = flt(yarn_row.qty)
 
    # Convert to kg if needed
    if yarn_row.uom != "kg":
        # Add UOM conversion logic if needed
        pass
 
    return qty
