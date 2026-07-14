# Whitelisted lot APIs: full trace, product re-assignment (audited),
# at-weaver balance (BOM-based yarn conversion).
import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_lot_trace(root_lot):
	"""Get full Stock Ledger Entry trace for all batches of a root lot."""
	frappe.has_permission("Root Lot", "read", throw=True)
	if not root_lot:
		return []
	batches = frappe.db.sql("""
		SELECT name, process_stage
		FROM `tabBatch`
		WHERE root_lot = %s
		ORDER BY process_stage
	""", root_lot, as_dict=True)
	batch_names = [b.name for b in batches]
	if not batch_names:
		return []
	sle_entries = frappe.db.sql("""
		SELECT sle.*, b.process_stage, b.root_lot
		FROM `tabStock Ledger Entry` sle
		JOIN `tabBatch` b ON b.name = sle.batch_no
		WHERE sle.batch_no IN ({})
		  AND sle.is_cancelled = 0
		ORDER BY sle.posting_date, sle.posting_time, sle.name
	""".format(','.join(['%s'] * len(batch_names))), batch_names, as_dict=True)
	return sle_entries


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
	"""kg of dyed yarn consumed per 1 unit of weaved pcs, from the item's BOM.

	The BOM is entered per its own `quantity` (e.g. a BOM that makes 100 pcs
	lists total yarn for 100). We divide by BOM quantity to get the per-piece
	yarn, so this works whether the BOM is built for 1 pc or many.
	"""
	if not weaved_item:
		return 0
	# Prefer the default active BOM, fall back to any active / submitted BOM
	bom = (frappe.db.get_value("BOM", {"item": weaved_item, "is_active": 1, "is_default": 1}, "name")
	       or frappe.db.get_value("BOM", {"item": weaved_item, "is_active": 1}, "name")
	       or frappe.db.get_value("BOM", {"item": weaved_item, "docstatus": 1}, "name"))
	if not bom:
		return 0
	filters = {"parent": bom}
	if dyed_yarn_item:
		filters["item_code"] = dyed_yarn_item
	rows = frappe.get_all("BOM Item", filters=filters,
	                      fields=["item_code", "stock_qty"])
	if not rows:
		return 0
	bom_qty = flt(frappe.db.get_value("BOM", bom, "quantity")) or 1
	return sum(flt(r.stock_qty) for r in rows) / bom_qty


@frappe.whitelist()
def at_weaver_balance(weaver=None, root_lot=None):
	"""Dyed yarn lying at each weaver, per lot per weaver.

	Columns (all yarn/kg based, except the pcs count):
	  dyed_yarn_sold_kg   - dyed yarn issued to the weaver (DN/SI out)
	  weaved_pcs_received - count of weaved pcs received back (display only)
	  consumed_equiv_kg   - yarn consumed per BOM = pcs * kg_per_pc
	  balance_at_weaver_kg- dyed_yarn_sold_kg - consumed_equiv_kg
	"""
	frappe.has_permission("Root Lot", "read", throw=True)
	sold = frappe.db.sql("""
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
	""", {"root_lot": root_lot} if root_lot else {}, as_dict=True)
	result = []
	for s in sold:
		weaver_name = s.weaver
		if weaver and weaver != weaver_name:
			continue
		# weaver as supplier (weaved pcs come back on a Purchase Receipt)
		weaver_supplier = weaver_name
		pr_rows = frappe.db.sql("""
			SELECT pri.item_code, SUM(pri.stock_qty) AS qty
			FROM `tabPurchase Receipt Item` pri
			JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
			WHERE pri.root_lot = %s AND pr.supplier = %s
			  AND pr.docstatus = 1 AND pr.is_return = 0
			GROUP BY pri.item_code
		""", (s.root_lot, weaver_supplier), as_dict=True)
		# count of weaved pcs (display only - NOT used for yarn math)
		total_pcs_received = sum(flt(r.qty) for r in pr_rows)
		# yarn consumed per BOM = pcs * kg_per_pc
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
