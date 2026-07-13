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
 
    Calculation:
    balance_at_weaver = dyed_yarn_sold - consumed_equiv
 
    Where:
    - dyed_yarn_sold = qty of dyed yarn sent to weaver (via DN/SI with weaver as customer)
    - weaved_pcs_received = total weaving pcs received from weaver (quantity)
    - consumed_equiv = weaving pcs received from weaver × kg_per_pc (from BOM)
 
    Args:
        weaver (str, optional): Filter by specific weaver (Customer name)
        root_lot (str, optional): Filter by specific root lot
 
    Returns:
        list: Rows with:
            - root_lot
            - weaver
            - dyed_yarn_sold_kg
            - weaved_pcs_received (NEW)
            - consumed_equiv_kg
            - balance_at_weaver_kg
    """
    frappe.has_permission("Root Lot", "read", throw=True)
 
    # Step 1: Get all weavers from PurchaseReceipts (weaving pcs received)
    # Assumption: Weaver Supplier name = Weaver Customer name
    weaver_suppliers = frappe.db.sql(
        """
        SELECT DISTINCT pr.supplier AS weaver_supplier
        FROM `tabPurchase Receipt` pr
        JOIN `tabPurchase Receipt Item` pri ON pr.name = pri.parent
        WHERE pri.root_lot IS NOT NULL
          AND pr.docstatus = 1
          AND pr.is_return = 0
        """, as_dict=True)
 
    result = []
 
    for w in weaver_suppliers:
        weaver_supplier = w.weaver_supplier
        # Assume the weaver's customer name is the same as their supplier name
        weaver_customer = weaver_supplier
 
        # Apply filter if user specified a weaver
        if weaver and weaver != weaver_customer:
            continue
 
        # Step 2: Get all dyed yarn sales to this weaver
        sold_data = frappe.db.sql(
            """
            SELECT b.root_lot,
                   SUM(ABS(sle.actual_qty)) AS sold_qty
            FROM `tabStock Ledger Entry` sle
            JOIN `tabBatch` b ON b.name = sle.batch_no
            LEFT JOIN `tabDelivery Note` dn ON (
                sle.voucher_type = 'Delivery Note'
                AND sle.voucher_no = dn.name
            )
            LEFT JOIN `tabSales Invoice` si ON (
                sle.voucher_type = 'Sales Invoice'
                AND sle.voucher_no = si.name
            )
            WHERE b.process_stage = 'DY'
              AND sle.is_cancelled = 0
              AND sle.actual_qty < 0
              AND sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
              AND (dn.customer = %s OR si.customer = %s)
            """ + ("AND b.root_lot = %s" if root_lot else "") + """
            GROUP BY b.root_lot
            """,
            (weaver_customer, weaver_customer, root_lot) if root_lot
            else (weaver_customer, weaver_customer),
            as_dict=True)
 
        # Step 3: For each lot-weaver combo, calculate balance
        for sale in sold_data:
            lot_code = sale.root_lot
            sold_kg = flt(sale.sold_qty)
 
            # Get weaving pcs received from this weaver for this lot
            pr_items = frappe.db.sql(
                """
                SELECT pri.item_code, SUM(pri.stock_qty) AS qty
                FROM `tabPurchase Receipt Item` pri
                JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
                WHERE pri.root_lot = %s
                  AND pr.supplier = %s
                  AND pr.docstatus = 1
                  AND pr.is_return = 0
                GROUP BY pri.item_code
                """, (lot_code, weaver_supplier), as_dict=True)
 
            # Convert pcs to kg equivalent
            consumed_kg = sum(
                flt(item.qty) * yarn_per_unit_from_bom(item.item_code)
                for item in pr_items)
 
            # NEW: Get total weaved pcs received
            total_pcs_received = sum(flt(item.qty) for item in pr_items)
 
            balance_kg = sold_kg - consumed_kg
 
            result.append({
                "root_lot": lot_code,
                "weaver": weaver_customer,
                "dyed_yarn_sold_kg": round(sold_kg, 2),
                "weaved_pcs_received": round(total_pcs_received, 2),  # NEW FIELD
                "consumed_equiv_kg": round(consumed_kg, 2),
                "balance_at_weaver_kg": round(balance_kg, 2),
            })
 
    return result
 
 
def yarn_per_unit_from_bom(weaving_item, dyed_yarn_item=None):
    """
    Get kg of yarn required per unit of weaving item, from BOM.
 
    Looks up the BOM for the weaving item, finds the dyed yarn input,
    and returns the qty_per_unit in kg.
 
    Args:
        weaving_item (str): Item code of the woven product (e.g., "Woven Panel Greige")
        dyed_yarn_item (str, optional): Item code of dyed yarn (e.g., "2/10s Cotton Yarn Beige").
                                        If None, searches for any dyed yarn input.
 
    Returns:
        float: kg of yarn per unit of weaving item. Returns 0 if no BOM found or no yarn input.
    """
    if not weaving_item:
        return 0
 
    # Find the BOM for this weaving item
    bom = frappe.db.get_value(
        "BOM",
        {"item": weaving_item, "docstatus": 1},  # docstatus=1 means submitted
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
        SELECT bi.item_code, bi.qty_per_unit, bi.uom
        FROM `tabBOM Item` bi
        WHERE """ + where_clause + """
        LIMIT 1
        """, params, as_dict=True)
 
    if not yarn_rows:
        return 0
 
    yarn_row = yarn_rows[0]
    qty = flt(yarn_row.qty_per_unit)
 
    # Convert to kg if needed
    # (Assuming yarn is always in kg; if other UOMs, add conversion logic)
    if yarn_row.uom != "kg":
        # TODO: add UOM conversion if BOM uses different units
        pass
 
    return qty
