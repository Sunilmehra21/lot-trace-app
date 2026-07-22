# -*- coding: utf-8 -*-
# Create Root Lot from EXISTING warehouse stock.
# Uses a REPACK Stock Entry: warehouse balance is unchanged (loose qty OUT,
# same qty IN under the new lot batch, same warehouse).

import frappe
from frappe import _
from frappe.utils import flt

from lot_trace.events import common, resolver, lot_factory


@frappe.whitelist()
def create_root_lot_from_stock(item_code, warehouse, qty):
    if "Lot Manager" not in frappe.get_roles() \
            and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Only Lot Manager can create a lot from stock."),
                     frappe.PermissionError)
    qty = flt(qty)
    if qty <= 0:
        frappe.throw(_("Quantity must be greater than zero."))

    rule, yarn_row = resolver.find_naming_rule_for_item(item_code)
    if not rule:
        frappe.throw(_(
            "{0} is not configured in any active Lot Naming Rule. "
            "Add it to a rule first.").format(item_code))

    available = flt(frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse},
        "actual_qty"))
    if available < qty:
        frappe.throw(_(
            "Only {0} available for {1} in {2}, cannot create a lot for {3}."
        ).format(available, item_code, warehouse, qty))

    decision = resolver.resolve_open_lot(item_code)
    if decision["action"] == "new":
        root_lot = lot_factory.create_root_lot(rule)
    elif decision["action"] == "reuse":
        root_lot = decision["root_lot"]
    else:
        frappe.throw(_(
            "{0} is a secondary yarn and no open lot is waiting for it. "
            "Create the primary yarn's lot first.").format(item_code))

    lot_code = frappe.db.get_value(
        "Root Lot", root_lot, "lot_code") or root_lot
    first_stage = common.first_stage_for_rule(rule)
    batch_no = common.create_stage_batch(
        lot_code, first_stage, item_code, yarn_row.item_abbr)

    se_name = _make_repack(item_code, warehouse, qty, batch_no)

    lot_factory.record_lot_receipt(
        root_lot=root_lot, yarn_item=item_code,
        item_abbr=yarn_row.item_abbr or "",
        batch_no=batch_no, received_kg=qty,
        source_doctype="Stock Entry", source_doc=se_name)

    return {
        "root_lot": root_lot, "lot_code": lot_code,
        "batch": batch_no, "stock_entry": se_name,
        "message": _(
            "Created {0} with batch {1} ({2} repacked, warehouse balance "
            "unchanged).").format(lot_code, batch_no, qty),
    }


def _make_repack(item_code, warehouse, qty, batch_no):
    se = frappe.get_doc({
        "doctype": "Stock Entry",
        "stock_entry_type": "Repack",
        "purpose": "Repack",
        "items": [
            {"item_code": item_code, "s_warehouse": warehouse, "qty": qty},
            {"item_code": item_code, "t_warehouse": warehouse, "qty": qty,
             "batch_no": batch_no, "is_finished_item": 1},
        ],
    })
    se.flags.ignore_permissions = True
    se.insert()
    se.submit()
    return se.name
