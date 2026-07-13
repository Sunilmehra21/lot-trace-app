"""
Report: At-Weaver Balance
Enhanced to include weaved pcs received count
"""

import frappe
from frappe import _


def execute(filters=None):
    """
    Generate At-Weaver Balance report with weaved pcs count.

    Columns:
    - Root Lot
    - Weaver
    - Dyed Yarn Sold (kg)
    - Weaved Pcs Received
    - Consumed Equiv (kg)
    - Balance at Weaver (kg)
    """
    if not filters:
        filters = {}

    columns = get_columns()
    data = get_data(filters)

    return columns, data


def get_columns():
    """Define report columns."""
    return [
        {
            "fieldname": "root_lot",
            "label": _("Root Lot"),
            "fieldtype": "Link",
            "options": "Root Lot",
            "width": 150,
        },
        {
            "fieldname": "weaver",
            "label": _("Weaver (Customer)"),
            "fieldtype": "Link",
            "options": "Customer",
            "width": 150,
        },
        {
            "fieldname": "dyed_yarn_sold_kg",
            "label": _("Dyed Yarn Sold (kg)"),
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "fieldname": "weaved_pcs_received",
            "label": _("Weaved Pcs Received"),
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "fieldname": "consumed_equiv_kg",
            "label": _("Consumed Equiv (kg)"),
            "fieldtype": "Float",
            "width": 140,
        },
        {
            "fieldname": "balance_at_weaver_kg",
            "label": _("Balance at Weaver (kg)"),
            "fieldtype": "Float",
            "width": 140,
        },
    ]


def get_data(filters):
    """
    Fetch data from at_weaver_balance() API function.
    """
    from lot_trace.api.lot import at_weaver_balance

    weaver = filters.get("weaver")
    root_lot = filters.get("root_lot")

    # Call the API function
    rows = at_weaver_balance(weaver=weaver, root_lot=root_lot)

    return rows
