# -*- coding: utf-8 -*-
# Phase 6.3 — Create Root Lot from existing stock (V2 rules).
#
# For yarn already in the warehouse (bought before lot-trace went live).
# Creates Root Lot + NT batch, then a REPACK Stock Entry that moves the
# loose (batchless) qty into the new batch. Warehouse balance is unchanged.

import frappe
from frappe.utils import flt

from lot_trace.events import resolver_v2
from lot_trace.events import lot_factory_v2


@frappe.whitelist()
def create_root_lot_from_stock(item_code, warehouse, qty):
    """Create a Root Lot for existing warehouse stock of a greige yarn."""
    qty = flt(qty)
    if qty <= 0:
        frappe.throw("Quantity must be greater than zero.")

    rule, yarn_row = resolver_v2.find_naming_rule_for_item(item_code)
    if not rule:
        frappe.throw(
            f"{item_code} is not configured in any active Lot Naming Rule. "
            f"Add it to a rule first (Manufacturing → Lot Naming Rule)."
        )

    available = flt(frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    ))
    if available < qty:
        frappe.throw(
            f"Only {available} available for {item_code} in {warehouse}, "
            f"cannot create a lot for {qty}."
        )

    role = (yarn_row or {}).get("role", "Primary")
    if role == "Primary":
        root_lot = lot_factory_v2.create_root_lot(rule)
    else:
        decision = resolver_v2.resolve_open_lot(item_code)
        if decision["action"] == "reuse":
            root_lot = decision["root_lot"]
        else:
            frappe.throw(
                f"{item_code} is a secondary yarn and no open lot is waiting "
                f"for it. Create the primary yarn's lot first."
            )

    lot_code = frappe.db.get_value("Root Lot", root_lot, "lot_code") or root_lot
    abbr = (yarn_row or {}).get("item_abbr")
    batch_name = resolver_v2.render_batch_name(lot_code, "NT", abbr=abbr)
    lot_factory_v2.ensure_batch(batch_name, item_code, root_lot, stage="NT")

    se = _make_repack(item_code, warehouse, qty, batch_name)

    lot_factory_v2.record_lot_receipt(
        root_lot=root_lot,
        yarn_item=item_code,
        item_abbr=abbr or "",
        nt_batch=batch_name,
        received_kg=qty,
        source_doctype="Stock Entry",
        source_doc=se,
    )

    return {
        "root_lot": root_lot,
        "lot_code": lot_code,
        "batch": batch_name,
        "stock_entry": se,
        "message": f"Created {lot_code} with batch {batch_name} "
                   f"({qty} kg repacked, warehouse balance unchanged).",
    }


def _make_repack(item_code, warehouse, qty, batch_name):
    """Repack: loose qty OUT, same qty IN under the new batch."""
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Repack",
        "purpose": "Repack",
        "items": [
            {   # consume the loose (batchless) stock
                "item_code": item_code,
                "s_warehouse": warehouse,
                "qty": qty,
                "batch_no": None,
            },
            {   # produce the same qty under the new lot batch
                "item_code": item_code,
                "t_warehouse": warehouse,
                "qty": qty,
                "batch_no": batch_name,
            },
        ],
    })
    se.insert(ignore_permissions=True)
    se.submit()
    return se.name
