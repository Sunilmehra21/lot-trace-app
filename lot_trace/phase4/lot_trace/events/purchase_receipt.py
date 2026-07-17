# Purchase Receipt:
#  A) greige yarn / fabric from supplier -> LOT BIRTH: Root Lot + first-stage batch
#     (first stage = the lot route's first stage; NT when no route — so a
#     product can start directly with FABRIC by giving its route a first
#     stage other than NT)
#  B) weaved pcs from weaver             -> BRIDGE: root_lot mandatory on row -> '-WV' batch

import frappe
from frappe import _
from frappe.utils import flt
from lot_trace.events.common import (
    create_stage_batch, find_naming_rule, first_stage_for_rule,
    log_exception, make_lot_code)

WEAVE_STAGE = "WV"


def before_submit(doc, method=None):
    """Validate and auto-populate batch_no for each item row."""
    if doc.is_return:
        return

    for row in doc.items:
        if row.get("batch_no"):
            continue

        # B) weaved pcs bridge ────────────────────────────────────────
        if is_weaving_row(row):
            if not row.get("root_lot"):
                frappe.throw(_(
                    "Row {0} ({1}): Root Lot is mandatory for weaved pcs receipts. "
                    "Select which lot's dyed yarn these pieces were woven from."
                ).format(row.idx, row.item_code))

            # Validate: weaving qty makes sense given the dyed yarn sold to this weaver
            validate_lot_reached_weaver(row.root_lot, row.idx)

            # CASE 2 — multi-lot weaving: if the Lot Consumption table is
            # filled, pcs were woven from dyed yarn of SEVERAL root lots.
            if not handle_multi_lot_weaving(doc, row):
                # single-lot path (default)
                validate_weaving_qty_vs_dyed(
                    root_lot=row.root_lot,
                    weaving_qty=row.qty,
                    weaving_item=row.item_code,
                    supplier=doc.supplier
                )

            # Create or link to the -WV (weaving) batch (under the PRIMARY lot)
            row.batch_no = create_stage_batch(row.root_lot, WEAVE_STAGE, row.item_code)
            continue

        # A) lot birth ────────────────────────────────────────────────
        # New material receipt from supplier: create Root Lot + first-stage
        # batch. The first stage comes from the rule's Lot Route (NT default;
        # a fabric-first product routes e.g. WV → CT → … and births at WV).
        rule = find_naming_rule(yarn_item=row.item_code)
        if not rule:
            continue  # not a traced item (no naming rule found)

        first_stage = first_stage_for_rule(rule)
        lot_code = make_lot_code(rule, doc.posting_date)
        create_root_lot(doc, row, rule, lot_code, first_stage)
        row.batch_no = create_stage_batch(lot_code, first_stage, row.item_code)
        row.root_lot = lot_code


def is_weaving_row(row):
    """Check if this PR row is a weaving pcs receipt (not a yarn receipt)."""
    if not row.get("purchase_order"):
        return False
    po_lot_stage = frappe.db.get_value(
        "Purchase Order", row.purchase_order, "lot_stage")
    return po_lot_stage == WEAVE_STAGE


def validate_lot_reached_weaver(root_lot, idx):
    """Validate that the root lot exists and has a DY (dyed yarn) batch."""
    if not frappe.db.exists("Root Lot", root_lot):
        frappe.throw(_(
            "Row {0}: Root Lot {1} does not exist"
        ).format(idx, root_lot))

    # Check: DY batch exists (dyed yarn was received for this lot)
    dy_batch = frappe.db.get_value(
        "Batch", {"root_lot": root_lot, "process_stage": "DY"})

    if not dy_batch:
        frappe.throw(_(
            "Row {0}: Root Lot {1} has no dyed-yarn (DY) batch yet. "
            "Dyed yarn must be received before weaving pcs can be traced."
        ).format(idx, root_lot))


def dyed_kg_sold_to_weaver(root_lot, supplier):
    """Total dyed yarn (kg) of this lot sold/issued to this weaver.

    Weaver duality: the DN/SI customer may be a different record than the
    PR supplier — resolved via Customer.represents_supplier + same name.
    """
    from lot_trace.api.lot import customers_for_supplier
    customers = customers_for_supplier(supplier) or [supplier]
    sold_qty = frappe.db.sql(
        """
        SELECT SUM(ABS(sle.actual_qty)) AS sold
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        LEFT JOIN `tabDelivery Note` dn ON (
            sle.voucher_type = 'Delivery Note' AND sle.voucher_no = dn.name)
        LEFT JOIN `tabSales Invoice` si ON (
            sle.voucher_type = 'Sales Invoice' AND sle.voucher_no = si.name)
        WHERE b.root_lot = %s
          AND b.process_stage = 'DY'
          AND sle.actual_qty < 0
          AND sle.voucher_type IN ('Delivery Note', 'Sales Invoice')
          AND COALESCE(dn.customer, si.customer) IN ({})
          AND sle.is_cancelled = 0
        """.format(", ".join(["%s"] * len(customers))),
        tuple([root_lot] + customers), as_dict=True)
    return flt(sold_qty[0].sold if sold_qty and sold_qty[0].sold else 0)


def handle_multi_lot_weaving(doc, row):
    """CASE 2: weaved pcs consumed dyed yarn from MULTIPLE root lots.

    The 'Lot Consumption' table on the Purchase Receipt lists every source
    lot with the kg consumed. The item row's root_lot is the PRIMARY lot
    (drives the -WV batch and the FG lot number). Secondary lots get an
    audit trail ("merged into" comment + Lot Exception).

    Returns True when the multi-lot path handled validation, False when the
    table is empty (caller falls back to the single-lot validation).
    """
    from lot_trace.api.lot import yarn_per_unit_from_bom

    entries = doc.get("lot_consumption") or []
    if not entries:
        return False

    primary = row.root_lot
    lots_in_table = [e.root_lot for e in entries]

    if primary not in lots_in_table:
        frappe.throw(_(
            "Lot Consumption table must include the primary Root Lot {0} "
            "(the one selected on the item row)."
        ).format(primary))

    # every lot must exist and have reached the weaver (DY batch present)
    for e in entries:
        validate_lot_reached_weaver(e.root_lot, row.idx)
        if flt(e.qty_kg) <= 0:
            frappe.throw(_(
                "Lot Consumption: Qty (Kg) must be positive for lot {0}."
            ).format(e.root_lot))

    # total consumed kg should match the BOM requirement for the pcs received
    total_kg = sum(flt(e.qty_kg) for e in entries)
    kg_per_pc = yarn_per_unit_from_bom(row.item_code, dyed_yarn_item=None)
    if kg_per_pc and kg_per_pc > 0:
        expected_kg = flt(row.qty) * kg_per_pc
        tolerance = max(0.5, expected_kg * 0.02)  # 2% or 0.5 kg
        if abs(total_kg - expected_kg) > tolerance:
            frappe.throw(_(
                "Lot Consumption total ({0} kg) does not match the BOM "
                "requirement for {1} pcs (~{2} kg). Correct the table or the "
                "received qty."
            ).format(round(total_kg, 2), row.qty, round(expected_kg, 2)))

    # each lot: consumed kg must not exceed dyed yarn STILL AVAILABLE with
    # this weaver (sold minus already consumed by earlier weaving PRs)
    from lot_trace.api.lot import get_dyed_available
    for e in entries:
        avail = get_dyed_available(e.root_lot, doc.supplier)
        if flt(e.qty_kg) > flt(avail["available_kg"]) + 0.1:
            frappe.throw(_(
                "Lot Consumption: lot {0} claims {1} kg consumed, but only "
                "{2} kg dyed yarn is still available with weaver {3} "
                "(sold {4} kg, already consumed {5} kg)."
            ).format(e.root_lot, round(flt(e.qty_kg), 2),
                     avail["available_kg"], doc.supplier,
                     avail["sold_kg"], avail["consumed_kg"]))

    # audit trail for the merge (secondary lots)
    for e in entries:
        if e.root_lot == primary:
            continue
        log_exception(
            exception_type="Lot Merge",
            severity="Warning",
            root_lot=e.root_lot,
            erp_doc_type=doc.doctype,
            erp_doc_name=doc.name,
            message=_("{0} kg dyed yarn of lot {1} consumed into weaving of "
                      "primary lot {2} (weaver {3}).")
            .format(round(flt(e.qty_kg), 2), e.root_lot, primary, doc.supplier))
        try:
            frappe.get_doc("Root Lot", e.root_lot).add_comment(
                "Comment",
                _("Merged: {0} kg dyed yarn consumed into lot {1} via {2}")
                .format(round(flt(e.qty_kg), 2), primary, doc.name))
        except Exception:
            pass

    return True


def validate_weaving_qty_vs_dyed(root_lot, weaving_qty, weaving_item, supplier):
    """
    Validate: weaving pcs qty makes sense given the dyed yarn sold to THIS weaver.

    Example:
    - Sold 400 kg dyed yarn to Weaver A
    - BOM: 0.5 kg per pc
    - Weaver A can only produce max 800 pcs (400 / 0.5)
    - If PR shows 900 pcs → throw error
    """
    from lot_trace.api.lot import yarn_per_unit_from_bom

    # Get BOM conversion: kg of yarn per 1 unit of weaving item
    kg_per_pc = yarn_per_unit_from_bom(weaving_item, dyed_yarn_item=None)
    if not kg_per_pc or kg_per_pc <= 0:
        # No BOM defined or no conversion found — skip validation
        return

    # Calculate: how much dyed yarn this many pcs would consume
    expected_kg = flt(weaving_qty) * kg_per_pc

    available_kg = dyed_kg_sold_to_weaver(root_lot, supplier)

    # Check: required kg <= available kg (with 0.1 kg tolerance for rounding)
    if expected_kg > available_kg + 0.1:
        frappe.throw(_(
            "Weaving pcs qty ({pcs}) requires ~{need} kg dyed yarn per BOM, "
            "but only {avail} kg was sold to weaver {weaver} under lot {lot}. "
            "Either reduce pcs qty or check the BOM yield (kg per pc)."
        ).format(
            pcs=round(weaving_qty, 2),
            need=round(expected_kg, 2),
            avail=round(available_kg, 2),
            weaver=supplier,
            lot=root_lot
        ))


def create_root_lot(doc, row, rule, lot_code, first_stage="NT"):
    """Create a new Root Lot record (lot birth from a material receipt)."""
    lot = frappe.new_doc("Root Lot")
    lot.update({
        "lot_code": lot_code,
        "product": rule.product,
        "yarn_item": row.item_code,
        "sales_order": rule.get("sales_order"),
        "supplier": doc.supplier,
        "supplier_invoice": doc.get("supplier_delivery_note") or doc.get("bill_no"),
        "purchase_receipt": doc.name,
        "received_qty": flt(row.qty),
        "uom": row.uom,
        "current_stage": first_stage,
        "status": "Open",
        # per-product stage sequence, copied from the naming rule at birth
        "route": rule.get("route"),
    })
    lot.flags.ignore_permissions = True
    lot.insert()


def on_submit(doc, method=None):
    """Handle submission: reflect purchase returns on Root Lot received qty."""
    if not doc.is_return:
        # Not a return — no special handling needed
        return

    # This is a purchase return of yarn: reduce Root Lot received qty
    for row in doc.items:
        rl = row.get("root_lot") or frappe.db.get_value(
            "Batch", row.get("batch_no"), "root_lot")

        if not rl:
            continue

        # Reduce the received qty by the return amount
        current_received = flt(frappe.db.get_value("Root Lot", rl, "received_qty"))
        return_qty = abs(flt(row.qty))

        frappe.db.set_value(
            "Root Lot", rl, "received_qty",
            current_received - return_qty,
            update_modified=False)


def on_cancel(doc, method=None):
    """Handle cancellation: cleanup Root Lot & batches if safe, else log exception."""
    if doc.is_return:
        # Cancelled return — no special handling
        return

    from lot_trace.events.common import first_stage_of_lot

    for row in doc.items:
        rl = row.get("root_lot")
        if not rl or not frappe.db.exists("Root Lot", rl):
            continue

        # Only process if this PR created this Root Lot
        if frappe.db.get_value("Root Lot", rl, "purchase_receipt") != doc.name:
            continue

        birth_stage = first_stage_of_lot(rl)

        # Check: does this lot have downstream batches beyond its birth stage?
        other_batches = frappe.get_all(
            "Batch",
            filters={"root_lot": rl, "process_stage": ["!=", birth_stage]},
            pluck="name")

        if other_batches:
            # Lot has moved downstream — block cancel and log exception
            log_exception(
                exception_type="Cancel With Downstream",
                severity="Error",
                root_lot=rl,
                erp_doc_type=doc.doctype,
                erp_doc_name=doc.name,
                message=_("PR cancelled but lot {0} already has downstream "
                          "batches: {1}").format(rl, ", ".join(other_batches)))
            continue

        # Lot is still at its birth stage and untouched — safe to cleanup
        birth_suffix = frappe.db.get_value(
            "Lot Process Stage", birth_stage, "batch_suffix") or birth_stage
        birth_batch = f"{rl}-{birth_suffix}"
        sle_count = frappe.db.count(
            "Stock Ledger Entry",
            {"batch_no": birth_batch, "is_cancelled": 0})

        if sle_count == 0:
            # No stock ledger entries — clean deletion
            frappe.delete_doc("Batch", birth_batch, ignore_permissions=True, force=True)
            frappe.delete_doc("Root Lot", rl, ignore_permissions=True, force=True)
        else:
            # Stock has been moved — mark as Short Closed
            frappe.db.set_value(
                "Root Lot", rl, "status", "Short Closed",
                update_modified=False)
