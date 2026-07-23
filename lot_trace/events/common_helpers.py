# Helper functions for lot traceability (Phase 5.1)
# Used by subcontracting_receipt.py and other handlers

import frappe


def get_root_lot_current_stage(root_lot):
	"""Get the current process stage of a root lot."""
	return frappe.db.get_value("Root Lot", root_lot, "current_stage")


def is_dyed_item(item_code):
	"""Check if item is a dyed/processed yarn.

	Looks for suffixes: -DYE-*, -DY-*, or matches patterns like:
	- RM-YN-COTTON-CN-DYE-BK (dyed)
	- RM-YN-COTTON-CN (raw)
	"""
	if not item_code:
		return False
	return "-DYE" in item_code.upper() or "-DY" in item_code.upper()


def is_cut_item(item_code):
	"""Check if item is a cut fabric."""
	if not item_code:
		return False
	return "-CT" in item_code.upper() or "CUT" in item_code.upper()


def extract_base_yarn_item(item_code):
	"""Extract base yarn code by removing dye/cut/color suffixes.

	Examples:
		RM-YN-COTTON-CN-DYE-BK → RM-YN-COTTON-CN
		RM-YN-CHENILLE-CN-DY → RM-YN-CHENILLE-CN
		RM-YN-COTTON-CN-CT-10PC → RM-YN-COTTON-CN
	"""
	if not item_code:
		return None

	import re
	# Match base item (ends with -CN, -RM, -SLK, etc.)
	match = re.match(r"(.*?-(?:CN|RM|WL|SLK|YRN|POL)?)(?:-DYE|-DY|-CT)?(?:-[A-Z]{2,})?$", item_code)
	if match:
		return match.group(1).rstrip("-")

	# Fallback: return as-is
	return item_code


def get_bom_items(finished_item):
	"""Get BOM items for a finished good.

	Returns list of {item_code, qty} from BOM child table.
	"""
	bom = frappe.db.get_value("Item", finished_item, "has_variants")
	if not bom:
		return []

	bom_doc = frappe.db.get_value(
		"BOM", {"item": finished_item, "docstatus": 1},
		["name"])
	if not bom_doc:
		return []

	return frappe.db.sql(f"""
		SELECT item_code, qty
		FROM `tabBOM Item`
		WHERE parent = '{bom_doc}' AND docstatus = 1
	""", as_dict=True)


def validate_yarn_item_link_to_lot(yarn_item, root_lot):
	"""Verify that a yarn item is linked to (and sourced from) a root lot.

	Used in multi-yarn weaving to ensure the yarn came from this specific lot.
	"""
	# Get the yarn item linked to this root lot
	linked_item = frappe.db.get_value("Root Lot", root_lot, "yarn_item")
	if not linked_item:
		return False

	# Check if requested yarn item matches (could be dyed version)
	base_requested = extract_base_yarn_item(yarn_item)
	base_linked = extract_base_yarn_item(linked_item)

	return base_requested == base_linked
