"""
lot_trace/report/at_weaver_balance/at_weaver_balance.py
Report query file for At-Weaver Balance Report.
Columns:

Root Lot
Weaver (Customer)
Dyed Yarn Sold (kg)
Weaved Pcs Received (NEW)
Consumed per BOM (kg)
Balance at Weaver (kg)
"""

import frappe
from frappe import _
def execute(filters=None):
"""
Execute report with filters.
Returns columns and data.
"""
if not filters:
filters = {}
columns = get_columns()
data = get_data(filters)

return columns, data
def get_columns():
"""
Define report columns.
"""
return [
{
"fieldname": "root_lot",
"label": _("Root Lot"),
"fieldtype": "Link",
"options": "Root Lot",
"width": 130,
},
{
"fieldname": "weaver",
"label": _("Weaver"),
"fieldtype": "Link",
"options": "Customer",
"width": 150,
},
{
"fieldname": "dyed_yarn_sold_kg",
"label": _("Dyed Yarn Sold (kg)"),
"fieldtype": "Float",
"width": 130,
},
{
"fieldname": "weaved_pcs_received",
"label": _("Weaved Pcs Received"),
"fieldtype": "Float",
"width": 140,
},
{
"fieldname": "consumed_equiv_kg",
"label": _("Consumed per BOM (kg)"),
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
