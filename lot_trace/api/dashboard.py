# -*- coding: utf-8 -*-
# Order Lot Overview API: per-sales-order lot totals.

import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_order_overview(sales_order=None, customer=None):
    frappe.has_permission("Root Lot", "read", throw=True)

    filters = {}
    if sales_order:
        filters["sales_order"] = sales_order

    lots = frappe.get_all(
        "Root Lot", filters=filters,
        fields=["name", "product", "sales_order", "status", "current_stage",
                "received_qty", "uom", "yarn_in_process_qty", "weaved_pcs",
                "fg_qty", "dispatched_qty", "intake_complete"],
        order_by="sales_order, name")

    orders = {}
    for lot in lots:
        so = lot.sales_order or "(no sales order)"
        if customer and so != "(no sales order)":
            so_customer = frappe.db.get_value("Sales Order", so, "customer")
            if so_customer != customer:
                continue
        bucket = orders.setdefault(so, {
            "sales_order": so,
            "customer": (frappe.db.get_value("Sales Order", so, "customer")
                         if so != "(no sales order)" else None),
            "lots": [],
            "totals": {"received_qty": 0, "yarn_in_process_qty": 0,
                       "weaved_pcs": 0, "fg_qty": 0, "dispatched_qty": 0},
        })
        bucket["lots"].append(lot)
        for f in bucket["totals"]:
            bucket["totals"][f] += flt(lot.get(f))

    for bucket in orders.values():
        bucket["totals"] = {k: round(v, 2)
                            for k, v in bucket["totals"].items()}
    return list(orders.values())
