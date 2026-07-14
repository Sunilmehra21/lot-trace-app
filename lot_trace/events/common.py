# Shared helpers: lot numbering, stage batches, single-lot guard, exceptions.

import frappe
from frappe import _
from frappe.utils import flt, getdate

EPS = 1e-6


def get_settings():
    return frappe.get_cached_doc("Lot Trace Settings")


# ----------------------------------------------------------------------
# Lot numbering:  {prefix}/{MMYY}/{###}   e.g. EL/TH/0726/001
# ----------------------------------------------------------------------
def find_naming_rule(yarn_item=None, product=None, customer=None):
    """Find the applicable Lot Naming Rule.

    Phase 2 selective traceability:
    - Item.lot_trace_enabled unchecked -> item is never traced
    - Customer.lot_trace_enabled (when a customer is resolvable) -> only
      opted-in customers are traced. If no customer context, rule applies.
    """
    # item-level opt-out
    if yarn_item:
        item_enabled = frappe.db.get_value("Item", yarn_item, "lot_trace_enabled")
        if item_enabled is not None and not int(item_enabled or 0):
            return None

    filters = {"active": 1}
    if product:
        filters["product"] = product
    elif yarn_item:
        filters["yarn_item"] = yarn_item
    name = frappe.db.get_value("Lot Naming Rule", filters)
    if not name:
        return None
    rule = frappe.get_cached_doc("Lot Naming Rule", name)

    # customer-level opt-in (checked only when a customer is known)
    rule_customer = customer or rule.get("customer")
    if rule_customer:
        cust_enabled = frappe.db.get_value(
            "Customer", rule_customer, "lot_trace_enabled")
        if cust_enabled is not None and not int(cust_enabled or 0):
            return None

    return rule


def make_lot_code(rule, posting_date):
    d = getdate(posting_date)
    period = f"{d.month:02d}{str(d.year)[2:]}"
    prefix = f"{rule.prefix}/{period}/"
    last = frappe.db.sql(
        """SELECT name FROM `tabRoot Lot`
           WHERE name LIKE %s ORDER BY name DESC LIMIT 1""",
        prefix + "%")
    nxt = 1
    if last:
        try:
            nxt = int(last[0][0].rsplit("/", 1)[1]) + 1
        except (ValueError, IndexError):
            nxt = frappe.db.count("Root Lot", {"name": ["like", prefix + "%"]}) + 1
    return f"{prefix}{str(nxt).zfill(rule.counter_digits or 3)}"


# ----------------------------------------------------------------------
# Stage batch factory:  batch_id = {root_lot}-{suffix}
# ----------------------------------------------------------------------
def create_stage_batch(root_lot, stage_code, item_code):
    stage = frappe.get_cached_doc("Lot Process Stage", stage_code)
    batch_id = f"{root_lot}-{stage.batch_suffix}"

    existing = frappe.db.get_value("Batch", batch_id, ["item"], as_dict=True)
    if existing:
        if existing.item != item_code:
            # same lot reaches same stage with a different item (rare) -> item-suffixed id
            batch_id = f"{root_lot}-{stage.batch_suffix}-{frappe.scrub(item_code)[:8].upper()}"
            if frappe.db.exists("Batch", batch_id):
                return batch_id
        else:
            return batch_id

    batch = frappe.new_doc("Batch")
    batch.batch_id = batch_id
    batch.item = item_code
    batch.root_lot = root_lot
    batch.process_stage = stage_code
    batch.flags.ignore_permissions = True
    batch.insert()

    # advance the lot's current stage (only forward)
    cur = frappe.db.get_value("Root Lot", root_lot, "current_stage")
    cur_seq = frappe.db.get_value("Lot Process Stage", cur, "sequence") if cur else 0
    if (stage.sequence or 0) >= (cur_seq or 0):
        frappe.db.set_value("Root Lot", root_lot,
                            {"current_stage": stage_code, "status": "In Process"},
                            update_modified=False)
    return batch_id


def get_root_lot_of_batch(batch_no):
    if not batch_no:
        return None
    return frappe.db.get_value("Batch", batch_no, "root_lot")


def next_stage_after(stage_code):
    seq = frappe.db.get_value("Lot Process Stage", stage_code, "sequence") or 0
    nxt = frappe.get_all("Lot Process Stage",
                         filters={"sequence": [">", seq], "active": 1},
                         order_by="sequence asc", limit=1, pluck="name")
    return nxt[0] if nxt else None


# ----------------------------------------------------------------------
# Single-lot-per-transaction guard (confirmed business rule)
# ----------------------------------------------------------------------
def collect_root_lots(doc, batch_field="batch_no", tables=("items",)):
    lots = set()
    for table in tables:
        for row in doc.get(table) or []:
            rl = get_root_lot_of_batch(row.get(batch_field))
            if rl:
                lots.add(rl)
    return lots


def enforce_single_lot(doc, lots):
    """Three-mode mixing policy (Phase 2).

    - Block: reject mixed lots; Lot Manager may tick 'Allow Mixed Lots'
      (override is logged as an exception).
    - Warn: allowed, always logged as an exception.
    - Allow: allowed silently, nothing logged.
    """
    if len(lots) <= 1:
        return
    policy = get_settings().mixing_policy or "Block"

    if policy == "Allow":
        return  # no restriction, no logging

    allow_override = bool(doc.get("allow_mixed_lots"))
    if policy == "Block" and not allow_override:
        frappe.throw(_(
            "Lot mixing not allowed: this document touches {0} root lots ({1}). "
            "Split into one document per lot, or a Lot Manager can tick "
            "'Allow Mixed Lots' (logged)."
        ).format(len(lots), ", ".join(sorted(lots))))
    if allow_override and "Lot Manager" not in frappe.get_roles():
        frappe.throw(_("Only a Lot Manager may use 'Allow Mixed Lots'."))
    log_exception(
        "Mixed Lots Override" if allow_override else "Mixed Lots Warning",
        "Warning",
        erp_doc_type=doc.doctype, erp_doc_name=doc.name,
        message=_("Document touches root lots: {0}").format(", ".join(sorted(lots))))


# ----------------------------------------------------------------------
# Exceptions
# ----------------------------------------------------------------------
def log_exception(exception_type, severity, message="", root_lot=None,
                  erp_doc_type=None, erp_doc_name=None):
    try:
        te = frappe.new_doc("Lot Exception")
        te.update({
            "exception_type": exception_type, "severity": severity,
            "message": message, "root_lot": root_lot,
            "erp_doc_type": erp_doc_type, "erp_doc_name": erp_doc_name,
        })
        te.flags.ignore_permissions = True
        te.insert()
    except Exception:
        frappe.log_error(title="Lot Exception insert failed",
                         message=frappe.get_traceback())


# ----------------------------------------------------------------------
# Loss check (input vs output, same UOM stages like dyeing)
# ----------------------------------------------------------------------
def check_stage_loss(root_lot, stage_code, input_qty, output_qty,
                     erp_doc_type=None, erp_doc_name=None):
    stage = frappe.get_cached_doc("Lot Process Stage", stage_code)
    tol = flt(stage.expected_loss_pct)
    if not flt(input_qty) or tol <= 0:
        return
    loss_pct = (flt(input_qty) - flt(output_qty)) / flt(input_qty) * 100
    if loss_pct > tol + 0.01:
        log_exception("Loss Out of Tolerance", "Warning", root_lot=root_lot,
                      erp_doc_type=erp_doc_type, erp_doc_name=erp_doc_name,
                      message=_("Stage {0}: loss {1}% exceeds tolerance {2}% "
                                "(in {3}, out {4})")
                      .format(stage_code, round(loss_pct, 2), tol,
                              input_qty, output_qty))
