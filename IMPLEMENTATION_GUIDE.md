# Lot Trace Implementation Guide

## Overview
This guide addresses the three core requirements for making Lot Trace optional and scalable:
1. Selective Traceability (per Customer, Item, Sales Order)
2. Lot Mixing Policy Configuration
3. Data Lifecycle & Archival

---

## 1. Selective Traceability – Trace Only Selected Customers/Items

### Problem
Currently, if a Lot Naming Rule exists for an item, ALL purchases are traced. This causes:
- Unnecessary overhead for low-value items (samples, testing)
- Inability to trace per customer (premium vs bulk buyers)
- Audit noise from non-critical lots

### Solution: Customer-Level & Item-Level Opt-In

#### Step 1: Add Custom Fields to Customer
Add a checkbox to allow customers to opt into traceability:

```python
# bench console or migration script
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Customer",
    "fieldname": "lot_trace_enabled",
    "fieldtype": "Check",
    "label": "Enable Lot Traceability",
    "description": "If checked, all purchases for this customer will be traced with Root Lot tracking",
    "default": 0,
}).insert()
```

#### Step 2: Add Custom Field to Item
Allow selective item-level traceability override:

```python
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Item",
    "fieldname": "lot_trace_enabled",
    "fieldtype": "Check",
    "label": "Enable Lot Traceability",
    "description": "If unchecked, this item will NOT be traced even if Lot Naming Rule exists",
    "default": 1,
}).insert()
```

#### Step 3: Update find_naming_rule() in common.py

```python
def find_naming_rule(yarn_item=None, product=None, supplier=None):
    """Find applicable Lot Naming Rule with scope filtering."""
    filters = {"active": 1, "enabled": 1}
    
    if product:
        filters["product"] = product
    elif yarn_item:
        filters["yarn_item"] = yarn_item
    else:
        return None
    
    rule_name = frappe.db.get_value("Lot Naming Rule", filters)
    if not rule_name:
        return None
    
    rule = frappe.get_cached_doc("Lot Naming Rule", rule_name)
    
    # Check supplier scope
    if supplier and rule.get("apply_to_suppliers"):
        allowed_suppliers = [r.supplier for r in rule.apply_to_suppliers]
        if supplier not in allowed_suppliers:
            return None
    
    return rule
```

#### Step 4: Update purchase_receipt.before_submit()

```python
def before_submit(doc, method=None):
    if doc.is_return:
        return

    for row in doc.items:
        if row.get("batch_no"):
            continue

        # Check item-level traceability override
        if not frappe.db.get_value("Item", row.item_code, "lot_trace_enabled"):
            continue

        # B) weaved pcs bridge
        if is_weaving_row(row):
            row.batch_no = create_stage_batch(row.root_lot, WEAVE_STAGE, row.item_code)
            continue

        # A) yarn lot birth
        rule = find_naming_rule(
            yarn_item=row.item_code,
            supplier=doc.supplier
        )
        if not rule:
            continue

        lot_code = make_lot_code(rule, doc.posting_date)
        create_root_lot(doc, row, rule, lot_code)
        row.batch_no = create_stage_batch(lot_code, FIRST_STAGE, row.item_code)
        row.root_lot = lot_code
```

---

## 2. Lot Mixing Policy Configuration

### Problem
Currently mixing_policy only has "Block" or "Warn". Needs a third mode for complete flexibility.

### Solution: Three-Mode Mixing Policy

#### Update enforce_single_lot() in common.py

```python
def enforce_single_lot(doc, lots):
    """
    Enforce single root lot per transaction based on policy.
    
    Policy modes:
    - Block: Always reject mixed lots (unless Lot Manager overrides)
    - Warn: Allow but log exception
    - Allow: No restriction
    """
    if len(lots) <= 1:
        return
    
    policy = get_settings().mixing_policy or "Block"
    allow_override = bool(doc.get("allow_mixed_lots"))
    
    if policy == "Block":
        if not allow_override:
            frappe.throw(_(
                "Lot mixing not allowed: this document touches {0} root lots ({1}). "
                "Split into one document per lot, or a Lot Manager can tick "
                "'Allow Mixed Lots' (logged)."
            ).format(len(lots), ", ".join(sorted(lots))))
        if "Lot Manager" not in frappe.get_roles():
            frappe.throw(_("Only a Lot Manager may use 'Allow Mixed Lots'."))
    
    elif policy == "Warn":
        # Always log, allow to proceed
        log_exception(
            "Mixed Lots Warning",
            "Warning",
            erp_doc_type=doc.doctype,
            erp_doc_name=doc.name,
            message=_("Document touches root lots: {0}").format(", ".join(sorted(lots))),
            auto_resolve=True)
    
    elif policy == "Allow":
        # Silent pass — no logging
        pass
```

---

## 3. Data Lifecycle & Archival – Archive After 1 Year

### Problem
Stock Ledger Entries and Lot Exceptions accumulate indefinitely, slowing down reports after 2–3 years.

### Solution: Soft Delete with Archival Job

#### Create Scheduled Job

```python
# lot_trace/events/archive_job.py

import frappe
from frappe.utils import add_months, today

def archive_completed_lots():
    """
    Monthly job: Archive completed lots older than 12 months.
    Marks records as archived without deleting them (audit trail intact).
    """
    settings = frappe.get_doc("Lot Trace Settings")
    if not settings.enable_auto_archival:
        return
    
    months = settings.archive_completed_lots_after_months or 12
    cutoff_date = add_months(today(), -months)
    
    # Archive Root Lots (completed, no open exceptions)
    lots_to_archive = frappe.get_all(
        "Root Lot",
        filters={
            "status": "Completed",
            "is_archived": 0,
            "modified": ["<", cutoff_date]
        },
        pluck="name"
    )
    
    for lot in lots_to_archive:
        open_exc = frappe.db.count(
            "Lot Exception",
            {"root_lot": lot, "resolved": 0}
        )
        if open_exc == 0:
            frappe.db.set_value("Root Lot", lot, "is_archived", 1, update_modified=False)
    
    # Archive resolved exceptions
    frappe.db.sql("""
        UPDATE `tabLot Exception`
        SET is_archived = 1
        WHERE resolved = 1 AND is_archived = 0 AND modified < %s
    """, cutoff_date)
    
    frappe.logger().info(
        f"Archived {len(lots_to_archive)} completed lots older than {cutoff_date}"
    )
```

#### Update hooks.py

```python
scheduled_jobs = [
    {
        "method": "lot_trace.events.archive_job.archive_completed_lots",
        "cron": "0 2 1 * *"  # 1st of month at 2 AM
    }
]
```

#### Update Reports

```python
# lot_trace/api/lot.py

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
    
    placeholders = ','.join(['%s'] * len(batch_names))
    sle_entries = frappe.db.sql(f"""
        SELECT sle.*, b.process_stage, b.root_lot, COALESCE(sle.is_archived, 0) as is_archived
        FROM `tabStock Ledger Entry` sle
        JOIN `tabBatch` b ON b.name = sle.batch_no
        WHERE sle.batch_no IN ({placeholders})
          AND sle.is_cancelled = 0
        ORDER BY sle.posting_date, sle.posting_time, sle.name
    """, batch_names, as_dict=True)
    
    return sle_entries
```

---

## 4. Implementation Checklist

### Phase 1: Customer/Item-Level Opt-In
- [ ] Add custom field: Customer.lot_trace_enabled
- [ ] Add custom field: Item.lot_trace_enabled
- [ ] Update find_naming_rule() in common.py
- [ ] Update purchase_receipt.before_submit()
- **Risk:** Low; purely additive

### Phase 2: Mixing Policy Modes
- [ ] Update mixing_policy in Lot Trace Settings (Block, Warn, Allow)
- [ ] Update enforce_single_lot() with three-mode logic
- [ ] Add allow_mixed_lots field to Stock Entry, Subcontracting Receipt
- **Risk:** Medium; change existing logic

### Phase 3: Data Archival
- [ ] Add is_archived custom field to: Root Lot, Lot Exception
- [ ] Create archive_job.py with scheduled function
- [ ] Update hooks.py with scheduled_jobs
- [ ] Update reports to include is_archived column
- [ ] Add archival settings to Lot Trace Settings
- **Risk:** Low; defaults to disabled

---

## 5. FAQ

**Q: Will traceability slow down performance?**  
A: No. Uses native Batch records (~2KB per lot). Queries indexed on batch_no, root_lot.

**Q: Can I retroactively trace historical lots?**  
A: Yes. Create migration script to backfill root_lot on Batch records from historical SLEs.

**Q: What if a lot spans multiple customers?**  
A: Not supported (one lot = one product path). Use separate Lot Naming Rules for different brands.

**Q: How do I restore archived data?**  
A: Set is_archived=0 on Root Lot record. Soft delete is fully reversible.
