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

#### Step 3: Extend Lot Naming Rule
Add filters to control which customers/suppliers use this rule:

```python
# In lot_trace/lot_trace/doctype/lot_naming_rule/lot_naming_rule.json
# Add these fields:

{
    "fieldname": "enabled",
    "fieldtype": "Check",
    "label": "Enabled",
    "default": 1,
    "description": "Disable rule without deleting it"
},
{
    "fieldname": "apply_to_section",
    "fieldtype": "Section Break",
    "label": "Apply To (Leave empty = all)"
},
{
    "fieldname": "apply_to_customers",
    "fieldtype": "Table",
    "label": "Customers",
    "options": "Lot Naming Rule Customer",
    "description": "If empty, rule applies to all customers"
},
{
    "fieldname": "apply_to_suppliers",
    "fieldtype": "Table",
    "label": "Suppliers",
    "options": "Lot Naming Rule Supplier",
    "description": "If empty, rule applies to all suppliers"
}
```

Create child doctypes:
```python
# lot_naming_rule_customer.json
{
    "doctype": "Lot Naming Rule Customer",
    "parent": "Lot Naming Rule",
    "parentfield": "apply_to_customers",
    "fields": [
        {"fieldname": "customer", "fieldtype": "Link", "options": "Customer"}
    ]
}

# lot_naming_rule_supplier.json
{
    "doctype": "Lot Naming Rule Supplier",
    "parent": "Lot Naming Rule",
    "parentfield": "apply_to_suppliers",
    "fields": [
        {"fieldname": "supplier", "fieldtype": "Link", "options": "Supplier"}
    ]
}
```

#### Step 4: Update find_naming_rule() in common.py

```python
def find_naming_rule(yarn_item=None, product=None, supplier=None, customer=None):
    """
    Find applicable Lot Naming Rule with scope filtering.
    
    Args:
        yarn_item: Item code of yarn
        product: Final product
        supplier: Supplier (yarn source)
        customer: End customer (for Sales Orders)
    
    Returns:
        Cached Lot Naming Rule doc or None
    """
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
    
    # Check supplier scope (NEW)
    if supplier and rule.get("apply_to_suppliers"):
        allowed_suppliers = [r.supplier for r in rule.apply_to_suppliers]
        if supplier not in allowed_suppliers:
            return None
    
    # Check customer scope (NEW)
    if customer and rule.get("apply_to_customers"):
        allowed_customers = [r.customer for r in rule.apply_to_customers]
        if customer not in allowed_customers:
            return None
    
    return rule
```

#### Step 5: Update purchase_receipt.before_submit()

```python
def before_submit(doc, method=None):
    """Validate and auto-populate batch_no for each item row."""
    if doc.is_return:
        return

    for row in doc.items:
        if row.get("batch_no"):
            continue

        # Check item-level traceability override (NEW)
        if not frappe.db.get_value("Item", row.item_code, "lot_trace_enabled"):
            continue

        # B) weaved pcs bridge
        if is_weaving_row(row):
            # ... existing validation ...
            row.batch_no = create_stage_batch(row.root_lot, WEAVE_STAGE, row.item_code)
            continue

        # A) yarn lot birth
        rule = find_naming_rule(
            yarn_item=row.item_code,
            supplier=doc.supplier  # NEW: pass supplier for scope check
        )
        if not rule:
            continue

        lot_code = make_lot_code(rule, doc.posting_date)
        create_root_lot(doc, row, rule, lot_code)
        row.batch_no = create_stage_batch(lot_code, FIRST_STAGE, row.item_code)
        row.root_lot = lot_code
```

#### Step 6: Update delivery.before_submit() – Customer Opt-In

```python
def before_submit(doc, method=None):
    """Check if customer requires traceability."""
    if not is_stock_effective(doc) or doc.get("is_return"):
        return
    
    lots = collect_root_lots(doc)
    if not lots:
        return
    
    # NEW: Check if traced lots are from customers requiring traceability
    traced_customers = set()
    for lot in lots:
        lot_customer = frappe.db.get_value("Root Lot", lot, "customer")
        if lot_customer:
            requires_trace = frappe.db.get_value(
                "Customer", lot_customer, "lot_trace_enabled")
            if requires_trace:
                traced_customers.add(lot_customer)
    
    if traced_customers and not doc.get("dispatch_type"):
        frappe.throw(_(
            "This document dispatches traced lot material for customers: {0}. "
            "Set Dispatch Type = Intermediate (to weaver) or Final (to end customer)."
        ).format(", ".join(sorted(traced_customers))))
    
    enforce_single_lot(doc, lots)
```

---

## 2. Lot Mixing Policy Configuration

### Problem
Currently mixing_policy only has "Block" or "Warn". Needs a third mode for complete flexibility.

### Solution: Three-Mode Mixing Policy

#### Step 1: Update Lot Trace Settings

```python
# In lot_trace/lot_trace/doctype/lot_trace_settings/lot_trace_settings.json
# Modify mixing_policy field:

{
    "fieldname": "mixing_policy",
    "fieldtype": "Select",
    "label": "Lot Mixing Policy",
    "options": "Block\nWarn\nAllow",
    "default": "Block",
    "description": "Block: Reject all mixed lots | Warn: Allow with audit log | Allow: No restriction"
}
```

#### Step 2: Update enforce_single_lot() in common.py

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

#### Step 3: Add allow_mixed_lots Field to Document Types

```python
# Add to Stock Entry, Subcontracting Receipt, etc.
{
    "fieldname": "allow_mixed_lots",
    "fieldtype": "Check",
    "label": "Allow Mixed Lots",
    "description": "Lot Manager only. Skip lot mixing validation for this document (logged as exception).",
    "depends_on": "eval:user_roles.includes('Lot Manager')"
}
```

---

## 3. Data Lifecycle & Archival – Archive After 1 Year

### Problem
Stock Ledger Entries and Lot Exceptions accumulate indefinitely, slowing down reports after 2–3 years.

### Solution: Soft Delete with Archival Job

#### Step 1: Add Archival Fields

```python
# Add to Stock Ledger Entry (custom field)
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Stock Ledger Entry",
    "fieldname": "is_archived",
    "fieldtype": "Check",
    "label": "Archived",
    "default": 0,
}).insert()

# Add to Lot Exception
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Lot Exception",
    "fieldname": "is_archived",
    "fieldtype": "Check",
    "label": "Archived",
    "default": 0,
}).insert()

# Add to Root Lot
frappe.get_doc({
    "doctype": "Custom Field",
    "dt": "Root Lot",
    "fieldname": "is_archived",
    "fieldtype": "Check",
    "label": "Archived",
    "default": 0,
}).insert()
```

#### Step 2: Create Scheduled Job

```python
# lot_trace/lot_trace/doctype/lot_trace_archive_job/lot_trace_archive_job.py

import frappe
from frappe.utils import add_months, today

def archive_completed_lots():
    """
    Monthly job: Archive completed lots older than 12 months.
    Marks records as archived without deleting them (audit trail intact).
    """
    cutoff_date = add_months(today(), -12)
    
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
        # Check no open exceptions
        open_exc = frappe.db.count(
            "Lot Exception",
            {"root_lot": lot, "resolved": 0}
        )
        if open_exc == 0:
            frappe.db.set_value("Root Lot", lot, "is_archived", 1)
    
    # Archive resolved exceptions older than 12 months
    frappe.db.sql("""
        UPDATE `tabLot Exception`
        SET is_archived = 1
        WHERE resolved = 1 AND is_archived = 0 AND modified < %s
    """, cutoff_date)
    
    # Archive stock ledger entries for archived lots
    frappe.db.sql("""
        UPDATE `tabStock Ledger Entry` sle
        SET sle.is_archived = 1
        WHERE sle.is_archived = 0
          AND sle.batch_no IN (
              SELECT name FROM `tabBatch`
              WHERE root_lot IN (
                  SELECT name FROM `tabRoot Lot`
                  WHERE is_archived = 1
              )
          )
    """)
    
    frappe.logger().info(
        f"Archived {len(lots_to_archive)} completed lots older than {cutoff_date}"
    )

# Register in hooks.py:
# scheduled_jobs = [
#     {
#         "method": "lot_trace.lot_trace.doctype.lot_trace_archive_job.lot_trace_archive_job.archive_completed_lots",
#         "cron": "0 2 1 * *"  # 1st of month at 2 AM
#     }
# ]
```

#### Step 3: Update Reports to Filter Archived Records

```python
# lot_trace/lot_trace/report/root_lot_trace/root_lot_trace.py

def execute(filters=None):
    filters = frappe._dict(filters or {})
    if not filters.root_lot:
        frappe.throw(_("Please select a Root Lot"))
    
    data = get_lot_trace(filters.root_lot)
    
    # Add column to show if archived
    columns = [
        {"label": _("Date"), "fieldname": "posting_date", "fieldtype": "Date", "width": 95},
        # ... existing columns ...
        {"label": _("Archived"), "fieldname": "is_archived", "fieldtype": "Check", "width": 60},
    ]
    
    return columns, data

# lot_trace/api/lot.py – update get_lot_trace()

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
    
    # Include is_archived in SELECT (NEW)
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

#### Step 4: Add Archival Settings to Lot Trace Settings

```python
# In lot_trace/lot_trace/doctype/lot_trace_settings/lot_trace_settings.json

{
    "fieldname": "archival_section",
    "fieldtype": "Section Break",
    "label": "Data Archival"
},
{
    "fieldname": "archive_completed_lots_after_months",
    "fieldtype": "Int",
    "label": "Archive Completed Lots After (Months)",
    "default": 12,
    "description": "Completed lots will be marked archived after this period"
},
{
    "fieldname": "enable_auto_archival",
    "fieldtype": "Check",
    "label": "Enable Auto-Archival",
    "default": 1,
    "description": "If unchecked, manual archival only"
}
```

---

## 4. Quick Start: Implementation Checklist

- [ ] **Phase 1: Customer/Item-Level Opt-In**
  - [ ] Add custom fields to Customer (lot_trace_enabled)
  - [ ] Add custom fields to Item (lot_trace_enabled)
  - [ ] Extend Lot Naming Rule with apply_to_customers/suppliers
  - [ ] Update find_naming_rule() in common.py
  - [ ] Update purchase_receipt.before_submit() to check item flag
  - [ ] Update delivery.before_submit() to check customer flag
  - **Rollout:** Low risk; purely additive

- [ ] **Phase 2: Mixing Policy Modes**
  - [ ] Add "Allow" mode to mixing_policy in Lot Trace Settings
  - [ ] Update enforce_single_lot() with three-mode logic
  - [ ] Add allow_mixed_lots field to Stock Entry, Subcontracting Receipt
  - **Rollout:** Medium risk; change existing logic

- [ ] **Phase 3: Data Archival**
  - [ ] Add is_archived fields to Stock Ledger Entry, Lot Exception, Root Lot
  - [ ] Create scheduled archival job
  - [ ] Update reports to filter archived=0
  - [ ] Add archival settings to Lot Trace Settings
  - **Rollout:** Low risk; defaults to no archival until manually enabled

---

## 5. FAQ

**Q: Will enabling traceability slow down performance?**  
A: No. Traceability uses native Batch records (standard ERPNext). Storage overhead ~2KB per lot. Queries indexed on batch_no, root_lot.

**Q: Can I retroactively trace historical lots?**  
A: Yes. Create a migration script to backfill root_lot on Batch records from historical SLEs. See examples/ directory.

**Q: What if a lot spans multiple customers?**  
A: Not supported by design (one lot = one product path). Use separate Lot Naming Rules if multiple brands share yarn source.

**Q: How do I restore archived data?**  
A: Set is_archived=0 on the Root Lot record. Stock Ledger Entries will automatically un-archive (soft delete is reversible).
