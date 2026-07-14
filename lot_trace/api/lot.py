"""
lot_trace/api/lot.py
Complete API module with all functions:

get_lot_trace() — for Root Lot Trace report
at_weaver_balance() — for At-Weaver Balance report (with pcs column)
yarn_per_unit_from_bom() — BOM conversion calculation
reassign_lot() — admin function
"""

import frappe
from frappe import _
from frappe.utils import flt
@frappe.whitelist()
def get_lot_trace(root_lot):
"""
Get full Stock Ledger Entry trace for all batches of a root lot.
Returns raw movement history in chronological order.
Used by Root Lot Trace report.
"""
frappe.has_permission("Root Lot", "read", throw=True)

if not root_lot:
    return []

# Get all batches for this root lot
batches = frappe.db.sql(
    """
    SELECT name, process_stage
    FROM `tabBatch`
    WHERE root_lot = %s
    ORDER BY process_stage
    """, root_lot, as_dict=True)

batch_names = [b.name for b in batches]

if not batch_names:
    return []

# Get all SLE entries for these batches, ordered by date
sle_entries = frappe.db.sql(
    """
    SELECT sle.*, b.process_stage, b.root_lot
    FROM `tabStock Ledger Entry` sle
    JOIN `tabBatch` b ON b.name = sle.batch_no
    WHERE sle.batch_no IN ({})
      AND sle.is_cancelled = 0
    ORDER BY sle.posting_date, sle.posting_time, sle.name
    """.format(','.join(['%s'] * len(batch_names))),
    batch_names, as_dict=True)

return sle_entries
@frappe.whitelist()
def at_weaver_balance(weaver=None, root_lot=None):
"""
Dyed yarn lying at weavers, per lot per weaver.
Calculation:
balance_at_weaver = dyed_yarn_sold - consumed_equiv

Where:
- dyed_yarn_sold = qty of dyed yarn sent to weaver (via DN/SI) in kg
- weaved_pcs_received = total pcs received from weaver (display only)
- consumed_equiv = weaving pcs received × kg_per_pc (from BOM) in kg
- balance = dyed_yarn_sold - consumed_equiv in kg
"""
frappe.has_permission("Root Lot", "read", throw=True)

# Sales of dyed yarn (DY batches) per lot per weaver-customer
sold = frappe.db.sql(
    """
    SELECT b.root_lot, COALESCE(dn.customer, si.customer) AS weaver,
           SUM(ABS(sle.actual_qty)) AS sold_qty
    FROM `tabStock Ledger Entry` sle
    JOIN `tabBatch` b ON b.name = sle.batch_no
    LEFT JOIN `tabDelivery Note Item` dni ON sle.voucher_type = 'Delivery Note'
                                               AND sle.voucher_no = dni.parent
                                               AND b.name = dni.batch_no
    LEFT JOIN `tabDelivery Note` dn ON dni.parent = dn.name
    LEFT JOIN `tabSales Invoice Item` sii ON sle.voucher_type = 'Sales Invoice'
                                              AND sle.voucher_no = sii.parent
                                              AND b.name = sii.batch_no
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

    # Weaver supplier = weaver customer (assume same name)
    weaver_supplier = weaver_name

    # Get weaved pcs received from this weaver for this lot
    pr_rows = frappe.db.sql(
        """
        SELECT pri.item_code, SUM(pri.stock_qty) AS qty
        FROM `tabPurchase Receipt Item` pri
        JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
        WHERE pri.root_lot = %s AND pr.supplier = %s
          AND pr.docstatus = 1 AND pr.is_return = 0
        GROUP BY pri.item_code
        """, (s.root_lot, weaver_supplier), as_dict=True)

    # Calculate total pcs received (display only)
    total_pcs_received = sum(flt(r.qty) for r in pr_rows)

    # Calculate consumed kg: pcs × kg_per_pc from BOM
    # IMPORTANT: multiply pcs by kg_per_pc to get kg consumed
    consumed = sum(
        flt(r.qty) * yarn_per_unit_from_bom(r.item_code)
        for r in pr_rows)

    balance = flt(s.sold_qty) - consumed

    result.append({
        "root_lot": s.root_lot,
        "weaver": weaver_name,
        "dyed_yarn_sold_kg": round(flt(s.sold_qty), 2),
        "weaved_pcs_received": round(total_pcs_received, 2),
        "consumed_equiv_kg": round(consumed, 2),
        "balance_at_weaver_kg": round(balance, 2),
    })

return result
def yarn_per_unit_from_bom(weaving_item, dyed_yarn_item=None):
"""
Get kg of yarn required per unit of weaving item, from BOM.
Args:
    weaving_item (str): Item code (e.g., "Woven Panel Greige")
    dyed_yarn_item (str, optional): Yarn item code

Returns:
    float: kg of yarn per unit. Returns 0 if no BOM found.

Example:
    If BOM requires 0.5 kg yarn per panel:
    yarn_per_unit_from_bom("Woven Panel Greige") = 0.5
"""
if not weaving_item:
    return 0

# Find the BOM (must be submitted)
bom = frappe.db.get_value(
    "BOM",
    {"item": weaving_item, "docstatus": 1},
    ["name"])

if not bom:
    return 0

# Build query
where_clause = "bom_no = %s"
params = [bom]

if dyed_yarn_item:
    where_clause += " AND item_code = %s"
    params.append(dyed_yarn_item)

# Get BOM item
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
    # TODO: add UOM conversion if BOM uses different units
    pass

return qty
@frappe.whitelist()
def reassign_lot(root_lot, new_product):
"""
Lot Manager can divert lot to different product.
Creates audit log in Lot Exception.
"""
frappe.has_permission("Root Lot", "write", throw=True)
# Get current lot
lot = frappe.get_doc("Root Lot", root_lot)
old_product = lot.product

# Update product
lot.product = new_product
lot.save()

# Log as exception
from lot_trace.events.common import log_exception
log_exception(
    exception_type="Manual Override",
    severity="Info",
    root_lot=root_lot,
    erp_doc_type="Root Lot",
    erp_doc_name=root_lot,
    message=_("Lot re-assigned from product {0} to {1}").format(
        old_product, new_product))

return {"message": "Lot reassigned successfully"}
