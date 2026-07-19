"""
Create Root Lot from existing warehouse stock (Phase 4 A.4)

Use case: Start lot traceability with yarn already in inventory, without
a Purchase Receipt. Useful for internal transfers, old stock, or stock-take
scenarios.

Approach: Stock Entry (Repack) — reassigns qty to new batch without changing
warehouse balance. Semantically correct: "This yarn is now tracked under a new lot."

API: frappe.call('lot_trace.api.create_from_stock.create_root_lot_from_stock', ...)
"""

import frappe
from frappe import _
from frappe.utils import flt
from lot_trace.events.common import (
    create_stage_batch, find_naming_rule, first_stage_for_rule,
    make_lot_code)


@frappe.whitelist()
def create_root_lot_from_stock(item_code, warehouse, qty, product=None):
    """Create a Root Lot manually from existing stock inventory.

    Args:
        item_code: The yarn item code
        warehouse: Warehouse where stock exists
        qty: Quantity to allocate to this lot (in item's UOM)
        product: Optional product code; if not given, infer from item's product field

    Returns:
        {
            "root_lot": "MV/BG/0726/01",
            "batch": "MV/BG/0726/01-NT",
            "item": "RM-YN-...",
            "qty": 15000.0,
            "warehouse": "Weaving - WIP",
            "message": "Root Lot created successfully from stock."
        }

    Side effects:
        - Creates Root Lot doc
        - Creates Batch doc (NT stage, birth stage)
        - Creates Stock Entry (Repack type) to reassign qty to new batch
          (warehouse balance unchanged, batch linked, audit trail created)
    """
    frappe.has_permission("Root Lot", "create", throw=True)

    item_code = item_code.strip() if item_code else ""
    warehouse = warehouse.strip() if warehouse else ""
    qty = flt(qty)

    if not item_code:
        frappe.throw(_("Item code is required"))
    if not warehouse:
        frappe.throw(_("Warehouse is required"))
    if qty <= 0:
        frappe.throw(_("Quantity must be > 0"))

    if not frappe.db.exists("Item", item_code):
        frappe.throw(_("Item {0} does not exist").format(item_code))
    if not frappe.db.exists("Warehouse", warehouse):
        frappe.throw(_("Warehouse {0} does not exist").format(warehouse))

    # Check stock availability
    stock_qty = frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty") or 0.0
    if flt(stock_qty) < qty:
        frappe.throw(_(
            "Insufficient stock: {item} in {warehouse} has {stock} {uom}, "
            "but {qty} requested."
        ).format(
            item=item_code, warehouse=warehouse,
            stock=round(flt(stock_qty), 2),
            qty=round(qty, 2),
            uom=frappe.db.get_value("Item", item_code, "stock_uom") or "units"))

    # Find naming rule for this item
    rule = find_naming_rule(yarn_item=item_code)
    if not rule:
        frappe.throw(_(
            "No Lot Naming Rule found for item {0}. "
            "Please set up a rule first."
        ).format(item_code))

    # Create Root Lot
    first_stage = first_stage_for_rule(rule)
    lot_code = make_lot_code(rule, frappe.utils.nowdate())

    root_lot = frappe.new_doc("Root Lot")
    root_lot.update({
        "lot_code": lot_code,
        "product": product or rule.product,
        "yarn_item": item_code,
        "sales_order": rule.get("sales_order"),
        "supplier": "Internal Stock",
        "supplier_invoice": f"Repack {frappe.utils.nowdate()}",
        "received_qty": qty,
        "uom": frappe.db.get_value("Item", item_code, "stock_uom"),
        "current_stage": first_stage,
        "status": "Open",
        "route": rule.get("route"),
        "custom_created_from_stock": True,
    })
    root_lot.flags.ignore_permissions = True
    root_lot.insert()

    # Create batch (birth stage)
    batch_name = create_stage_batch(lot_code, first_stage, item_code)

    # Create Stock Entry (Repack type)
    # Repack reassigns qty to new batch without changing warehouse balance
    se = frappe.new_doc("Stock Entry")
    se.update({
        "doctype": "Stock Entry",
        "stock_entry_type": "Repack",
        "posting_date": frappe.utils.nowdate(),
        "posting_time": frappe.utils.nowtime(),
        "purpose": "Repack",
        "remarks": f"Create Root Lot: {lot_code} from existing warehouse stock",
    })

    # Outgoing: original item (from existing batch or no batch)
    se.append("items", {
        "item_code": item_code,
        "qty": qty,
        "uom": frappe.db.get_value("Item", item_code, "stock_uom"),
        "s_warehouse": warehouse,
        "batch_no": None,  # From unassigned/generic stock
        "basic_rate": frappe.db.get_value(
            "Stock Ledger Entry",
            {"item_code": item_code, "warehouse": warehouse, "is_cancelled": 0},
            "valuation_rate") or 0.0,
    })

    # Incoming: same item to new batch
    se.append("items", {
        "item_code": item_code,
        "qty": qty,
        "uom": frappe.db.get_value("Item", item_code, "stock_uom"),
        "t_warehouse": warehouse,
        "batch_no": batch_name,  # New batch (lot)
        "basic_rate": frappe.db.get_value(
            "Stock Ledger Entry",
            {"item_code": item_code, "warehouse": warehouse, "is_cancelled": 0},
            "valuation_rate") or 0.0,
    })

    se.flags.ignore_permissions = True
    se.insert()
    se.submit()

    return {
        "root_lot": lot_code,
        "batch": batch_name,
        "item": item_code,
        "qty": round(qty, 2),
        "warehouse": warehouse,
        "stock_entry": se.name,
        "message": _("Root Lot {0} created from stock. Repack {1} submitted.").format(
            lot_code, se.name)
    }
