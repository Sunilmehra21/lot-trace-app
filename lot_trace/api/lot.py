# Whitelisted lot APIs: full trace, product re-assignment (audited),
# at-weaver balance (BOM-based yarn conversion), weaver-aware link queries,
# dyed-yarn availability, and lot birth from existing stock.
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


def customers_for_supplier(supplier):
	"""Weaver duality: the customer records that represent this supplier.

	A weaver buys dyed yarn as a CUSTOMER and returns weaved pcs as a
	SUPPLIER. Resolution: Customer.represents_supplier = supplier, plus the
	same-name assumption (customer named exactly like the supplier).
	"""
	if not supplier:
		return []
	names = set(frappe.get_all(
		"Customer", filters={"represents_supplier": supplier}, pluck="name"))
	if frappe.db.exists("Customer", supplier):
		names.add(supplier)
	return list(names)


@frappe.whitelist()
def at_weaver_balance(weaver=None, root_lot=None):
	"""Dyed yarn lying at each weaver, per lot per weaver.

	Columns (all yarn/kg based, except the pcs count):
	  dyed_yarn_sold_kg   - dyed yarn issued to the weaver (DN/SI out)
	  weaved_pcs_received - count of weaved pcs received back (display only)
	  consumed_equiv_kg   - yarn consumed per BOM = pcs * kg_per_pc
	  balance_at_weaver_kg- dyed_yarn_sold_kg - consumed_equiv_kg

	`weaver` filter accepts a SUPPLIER name; sold rows carry CUSTOMER names,
	so the filter is resolved through customers_for_supplier() (fixes the
	filter never matching).
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

	# resolve the supplier-typed filter to the matching customer names.
	# Also accept a customer name typed directly (backward compatible).
	allowed_customers = None
	if weaver:
		allowed_customers = set(customers_for_supplier(weaver))
		allowed_customers.add(weaver)

	result = []
	for s in sold:
		weaver_name = s.weaver
		if allowed_customers is not None and weaver_name not in allowed_customers:
			continue
		# weaver as supplier (weaved pcs come back on a Purchase Receipt).
		# reverse-resolve: which supplier does this customer represent?
		weaver_supplier = (frappe.db.get_value(
			"Customer", weaver_name, "represents_supplier")
			or weaver_name)
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


@frappe.whitelist()
def get_dyed_available(root_lot, supplier):
	"""Dyed yarn of one lot still available with one weaver (supplier).

	available = dyed kg sold to the weaver's customer record
	          - kg already consumed by weaved pcs receipts (BOM equivalent
	            for single-lot PRs; Lot Consumption rows for multi-lot PRs).
	Used by the Purchase Receipt form to show live availability in the
	Lot Consumption (multi-lot weaving) table.
	"""
	frappe.has_permission("Root Lot", "read", throw=True)
	customers = customers_for_supplier(supplier)
	if not customers:
		return {"item": None, "sold_kg": 0, "consumed_kg": 0, "available_kg": 0}

	sold = frappe.db.sql("""
		SELECT SUM(ABS(sle.actual_qty)) AS sold
		FROM `tabStock Ledger Entry` sle
		JOIN `tabBatch` b ON b.name = sle.batch_no
		LEFT JOIN `tabDelivery Note` dn ON (
			sle.voucher_type = 'Delivery Note' AND sle.voucher_no = dn.name)
		LEFT JOIN `tabSales Invoice` si ON (
			sle.voucher_type = 'Sales Invoice' AND sle.voucher_no = si.name)
		WHERE b.root_lot = %s AND b.process_stage = 'DY'
		  AND sle.actual_qty < 0 AND sle.is_cancelled = 0
		  AND sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
		  AND COALESCE(dn.customer, si.customer) IN ({})
	""".format(", ".join(["%s"] * len(customers))),
		tuple([root_lot] + customers), as_dict=True)
	sold_kg = flt(sold[0].sold if sold and sold[0].sold else 0)

	# consumed via multi-lot weaving (Lot Consumption rows on submitted PRs)
	multi = frappe.db.sql("""
		SELECT SUM(lcd.qty_kg) AS kg
		FROM `tabLot Consumption Detail` lcd
		JOIN `tabPurchase Receipt` pr ON pr.name = lcd.parent
			AND lcd.parenttype = 'Purchase Receipt'
		WHERE lcd.root_lot = %s AND pr.supplier = %s AND pr.docstatus = 1
	""", (root_lot, supplier), as_dict=True)
	consumed_kg = flt(multi[0].kg if multi and multi[0].kg else 0)

	# consumed via single-lot weaving PRs (no Lot Consumption table):
	# BOM equivalent of the pcs received on those PRs
	single_rows = frappe.db.sql("""
		SELECT pri.item_code, SUM(pri.stock_qty) AS qty
		FROM `tabPurchase Receipt Item` pri
		JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
		WHERE pri.root_lot = %s AND pr.supplier = %s
		  AND pr.docstatus = 1 AND pr.is_return = 0
		  AND NOT EXISTS (
			SELECT 1 FROM `tabLot Consumption Detail` lcd
			WHERE lcd.parent = pr.name AND lcd.parenttype = 'Purchase Receipt')
		GROUP BY pri.item_code
	""", (root_lot, supplier), as_dict=True)
	for r in single_rows:
		consumed_kg += flt(r.qty) * yarn_per_unit_from_bom(r.item_code)

	dy_item = frappe.db.get_value(
		"Batch", {"root_lot": root_lot, "process_stage": "DY"}, "item")

	return {
		"item": dy_item,
		"sold_kg": round(sold_kg, 2),
		"consumed_kg": round(consumed_kg, 2),
		"available_kg": round(sold_kg - consumed_kg, 2),
	}


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def weaver_root_lot_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for Purchase Receipt row.root_lot / Lot Consumption.root_lot.

	Shows ONLY the root lots whose dyed yarn was sold (DN / SI) to the
	customer(s) representing the PR's supplier — instead of every lot.
	Falls back to all lots when no supplier context is available.
	"""
	supplier = (filters or {}).get("supplier")
	customers = customers_for_supplier(supplier) if supplier else []

	if not customers:
		return frappe.db.sql("""
			SELECT name, product FROM `tabRoot Lot`
			WHERE name LIKE %(txt)s
			ORDER BY name LIMIT %(start)s, %(page_len)s
		""", {"txt": f"%{txt}%", "start": start, "page_len": page_len})

	return frappe.db.sql("""
		SELECT DISTINCT b.root_lot,
		       CONCAT(ROUND(SUM(ABS(sle.actual_qty)), 1), ' kg dyed sold')
		FROM `tabStock Ledger Entry` sle
		JOIN `tabBatch` b ON b.name = sle.batch_no
		LEFT JOIN `tabDelivery Note` dn ON (
			sle.voucher_type = 'Delivery Note' AND sle.voucher_no = dn.name)
		LEFT JOIN `tabSales Invoice` si ON (
			sle.voucher_type = 'Sales Invoice' AND sle.voucher_no = si.name)
		WHERE b.process_stage = 'DY'
		  AND sle.actual_qty < 0 AND sle.is_cancelled = 0
		  AND sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
		  AND COALESCE(dn.customer, si.customer) IN ({placeholders})
		  AND b.root_lot LIKE %(txt)s
		GROUP BY b.root_lot
		ORDER BY b.root_lot
		LIMIT %(start)s, %(page_len)s
	""".format(placeholders=", ".join(["%({})s".format("c%d" % i)
	                                   for i in range(len(customers))])),
		dict({"c%d" % i: c for i, c in enumerate(customers)},
		     txt=f"%{txt}%", start=start, page_len=page_len))


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def dyed_item_query(doctype, txt, searchfield, start, page_len, filters):
	"""Link query for Lot Consumption Detail.dyed_yarn_item:
	only items that exist as DY-stage batches of the selected root lot."""
	root_lot = (filters or {}).get("root_lot")
	if not root_lot:
		return []
	return frappe.db.sql("""
		SELECT DISTINCT b.item, i.item_name
		FROM `tabBatch` b
		JOIN `tabItem` i ON i.name = b.item
		WHERE b.root_lot = %(root_lot)s AND b.process_stage = 'DY'
		  AND b.item LIKE %(txt)s
		LIMIT %(start)s, %(page_len)s
	""", {"root_lot": root_lot, "txt": f"%{txt}%",
	      "start": start, "page_len": page_len})


@frappe.whitelist()
def create_lot_from_stock(item_code, qty, warehouse, product=None,
                          posting_date=None):
	"""Lot birth from EXISTING stock (yarn already in the warehouse, not a
	fresh purchase).

	Creates the Root Lot + first-stage batch, then returns a DRAFT Repack
	Stock Entry that converts `qty` of the un-batched stock into the new
	lot batch. Review and submit the Stock Entry to complete the birth.
	"""
	if ("Lot Manager" not in frappe.get_roles()
			and "System Manager" not in frappe.get_roles()):
		frappe.throw(_("Only Lot Manager can create a lot from existing stock."),
		             frappe.PermissionError)
	qty = flt(qty)
	if qty <= 0:
		frappe.throw(_("Qty must be positive."))

	from lot_trace.events.common import (
		find_naming_rule, make_lot_code, create_stage_batch,
		first_stage_for_rule)

	rule = find_naming_rule(yarn_item=item_code, product=product)
	if not rule:
		frappe.throw(_(
			"No active Lot Naming Rule found for item {0}{1}. Create one first."
		).format(item_code, _(" / product ") + product if product else ""))

	posting_date = posting_date or frappe.utils.today()
	lot_code = make_lot_code(rule, posting_date)
	first_stage = first_stage_for_rule(rule)

	lot = frappe.new_doc("Root Lot")
	lot.update({
		"lot_code": lot_code,
		"product": rule.product,
		"yarn_item": item_code,
		"sales_order": rule.get("sales_order"),
		"supplier": None,
		"received_qty": qty,
		"uom": frappe.db.get_value("Item", item_code, "stock_uom"),
		"current_stage": first_stage,
		"status": "Open",
		"route": rule.get("route"),
	})
	lot.flags.ignore_permissions = True
	lot.insert()
	lot.add_comment("Comment", _(
		"Lot created from existing stock ({0} x {1} in {2}) by {3}"
	).format(qty, item_code, warehouse, frappe.session.user))

	batch_no = create_stage_batch(lot_code, first_stage, item_code)

	# Draft Repack: consume the un-batched stock, produce it into the lot batch
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = "Repack"
	se.posting_date = posting_date
	se.append("items", {
		"item_code": item_code, "qty": qty,
		"s_warehouse": warehouse,
	})
	se.append("items", {
		"item_code": item_code, "qty": qty,
		"t_warehouse": warehouse, "batch_no": batch_no,
		"is_finished_item": 1,
	})
	se.flags.ignore_permissions = True
	se.insert()

	return {"root_lot": lot_code, "batch": batch_no, "stock_entry": se.name}
