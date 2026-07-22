# -*- coding: utf-8 -*-
# Order Lot Overview report: lots grouped per Sales Order with a
# group summary row. Reuses lot_trace.api.dashboard.get_order_overview (P2/P3).

import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
    filters = frappe._dict(filters or {})
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "sales_order", "label": _("Sales Order"),
         "fieldtype": "Link", "options": "Sales Order", "width": 150},
        {"fieldname": "customer", "label": _("Customer"),
         "fieldtype": "Link", "options": "Customer", "width": 150},
        {"fieldname": "root_lot", "label": _("Root Lot"),
         "fieldtype": "Link", "options": "Root Lot", "width": 140},
        {"fieldname": "product", "label": _("Product"),
         "fieldtype": "Link", "options": "Item", "width": 150},
        {"fieldname": "status", "label": _("Status"),
         "fieldtype": "Data", "width": 100},
        {"fieldname": "current_stage", "label": _("Stage"),
         "fieldtype": "Data", "width": 70},
        {"fieldname": "received_qty", "label": _("Yarn Received (kg)"),
         "fieldtype": "Float", "width": 130},
        {"fieldname": "yarn_in_process_qty", "label": _("Yarn In Process (kg)"),
         "fieldtype": "Float", "width": 140},
        {"fieldname": "weaved_pcs", "label": _("Weaved (pcs)"),
         "fieldtype": "Float", "width": 110},
        {"fieldname": "fg_qty", "label": _("FG Qty"),
         "fieldtype": "Float", "width": 100},
        {"fieldname": "dispatched_qty", "label": _("Dispatched"),
         "fieldtype": "Float", "width": 100},
        {"fieldname": "intake_complete", "label": _("Intake Complete"),
         "fieldtype": "Check", "width": 110},
    ]


def get_data(filters):
    from lot_trace.api.dashboard import get_order_overview

    orders = get_order_overview(
        sales_order=filters.get("sales_order"),
        customer=filters.get("customer"))

    data = []
    for bucket in orders:
        so = bucket["sales_order"]
        so_link = so if so != "(no sales order)" else None
        for lot in bucket["lots"]:
            if filters.get("status") and lot.status != filters.status:
                continue
            data.append({
                "sales_order": so_link,
                "customer": bucket["customer"],
                "root_lot": lot.name,
                "product": lot.product,
                "status": lot.status,
                "current_stage": lot.current_stage,
                "received_qty": flt(lot.received_qty),
                "yarn_in_process_qty": flt(lot.yarn_in_process_qty),
                "weaved_pcs": flt(lot.weaved_pcs),
                "fg_qty": flt(lot.fg_qty),
                "dispatched_qty": flt(lot.dispatched_qty),
                "intake_complete": lot.intake_complete,
            })
        if len(bucket["lots"]) > 1 and not filters.get("status"):
            t = bucket["totals"]
            data.append({
                "sales_order": None,
                "customer": None,
                "root_lot": None,
                "product": _("TOTAL — {0}").format(so),
                "status": None,
                "current_stage": None,
                "received_qty": t["received_qty"],
                "yarn_in_process_qty": t["yarn_in_process_qty"],
                "weaved_pcs": t["weaved_pcs"],
                "fg_qty": t["fg_qty"],
                "dispatched_qty": t["dispatched_qty"],
                "intake_complete": None,
                "bold": 1,
            })
    return data
