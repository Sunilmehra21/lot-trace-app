# Lot Trace App - Complete Review & Recommendations

## Executive Summary

The Lot Trace app is a well-architected traceability system for ERPNext that tracks inventory through production stages using native Batch records. The current implementation is **feature-complete for basic use** but lacks flexibility for:
1. **Selective traceability** (some customers/items don't need tracing)
2. **Configurable mixing policies** (only Block or Warn, no Allow mode)
3. **Data lifecycle management** (unlimited growth of historical records)

This review identifies **10 issues** (3 critical, 4 high, 3 medium) with recommended fixes and implementation guidance.

---

# DETAILED FINDINGS

## 🔴 CRITICAL ISSUES

### 1. No Optional Traceability – All Items Traced

**Severity:** CRITICAL  
**Impact:** Overhead, audit noise, inability to trace per customer

**Current State:**
- If a Lot Naming Rule exists for an item, ALL purchases are traced
- No per-customer opt-in mechanism
- No per-item disable flag

**Problem Scenario:**
- Company supplies both IKEA (premium, requires traceability) and bulk buyers (don't need it)
- Currently, yarn for both customers is traced equally
- Results in data bloat and slower reports for non-critical lots

**Recommended Solution:**
Implement three-level opt-in:
1. **Item-level:** Add `lot_trace_enabled` checkbox to Item doctype (default: true)
2. **Customer-level:** Add `lot_trace_enabled` checkbox to Customer doctype (default: false)
3. **Supplier-level:** Extend Lot Naming Rule with `apply_to_suppliers` filter

**Implementation:** See IMPLEMENTATION_GUIDE.md, Section 1

**Code Changes Required:**
- 2 custom fields
- Update `find_naming_rule()` in common.py (~15 lines)
- Update `purchase_receipt.before_submit()` (~5 lines)
- Update `delivery.before_submit()` (~10 lines)

**Risk:** Low (purely additive)

---

### 2. Weaver Balance Report – No Customer-Level Segregation

**Severity:** CRITICAL  
**Impact:** Cannot segregate dyed yarn inventory by customer when same weaver works for multiple brands

**Current State:**
```python
def at_weaver_balance(weaver=None, root_lot=None):  # No customer param
```

**Problem Scenario:**
- Weaver X produces for both Brand A and Brand B
- Report shows "200kg at Weaver X" but doesn't distinguish which customer's yarn
- Impossible to reconcile inventory by customer

**Recommended Solution:**
Add `customer` parameter to filter by end customer:
```python
def at_weaver_balance(weaver=None, root_lot=None, customer=None):
    # ...
    WHERE ... AND rl.customer = %(customer)s
```

**Implementation:** See IMPLEMENTATION_GUIDE.md, Section 1.6 & api/lot.py

**Code Changes Required:**
- Add customer parameter (~5 lines)
- Add customer filter to SQL (~3 lines)
- Update report filter UI (+1 filter)

**Risk:** Low (backward compatible)

---

### 3. UOM Conversion – Silent Failures

**Severity:** CRITICAL  
**Impact:** Incorrect balance calculations if BOM items in non-kg units

**Current State (before fix):**
```python
if yarn_row.uom != "kg":
    pass  # BUG: ignores unit conversion!
return qty  # Returns unconverted qty
```

**Problem Scenario:**
- BOM specifies "0.5 meter per pc" but system treats as "0.5 kg per pc"
- At-Weaver Balance report calculates consumed = pcs × 0.5 kg instead of pcs × 0.5 meter
- Massive inventory imbalance in reports

**Status:** ✅ **FIXED in commit 11d932c**
- Implemented proper `get_conversion_factor()` with error handling
- Now converts all units to kg correctly
- Returns 0 on conversion failure (safe default)

---

## 🟠 HIGH PRIORITY ISSUES

### 4. Lot Mixing Policy – Incomplete Modes

**Severity:** HIGH  
**Impact:** Cannot disable lot mixing enforcement, forces all documents to be single-lot

**Current State:**
```python
if policy == "Block" and not allow_override:
    frappe.throw(...)  # Reject mixed lots
elif policy == "Warn":
    log_exception(...)  # Allow with logging
# No third mode (Allow without logging)
```

**Problem Scenario:**
- Bulk transfers don't need per-lot tracking
- System still enforces single-lot rule
- Workaround: managers must set `allow_mixed_lots` flag each time
- Creates audit noise (every transfer logged as "override")

**Recommended Solution:**
Add "Allow" mode to mixing_policy:
```python
if policy == "Block":  # Reject all mixed lots
    ...
elif policy == "Warn":   # Allow with audit log
    log_exception(...)
elif policy == "Allow":  # Silent pass (no logging)
    pass
```

**Implementation:** See IMPLEMENTATION_GUIDE.md, Section 2

**Code Changes Required:**
- Add "Allow" option to Lot Trace Settings mixing_policy field
- Update `enforce_single_lot()` (~10 lines)

**Risk:** Medium (changes existing behavior)

---

### 5. Lot Exception – Missing Root Lot Silently Fails

**Severity:** HIGH  
**Impact:** Subcontracting receipts without root lot proceed untraced, creating orphaned FG batches

**Current State (subcontracting_receipt.py, line 24–29):**
```python
if not lots:
    log_exception("Missing Root Lot", "Warning", ...)
    return  # Silently continues untraced!
```

**Problem Scenario:**
- Subcontractor receives dyed yarn without batch tracking
- Output is created with FG batch but no root lot linkage
- Report shows "Untraced FG" — no way to trace back to source yarn

**Recommended Solution:**
Make behavior configurable in Lot Trace Settings:
- **Block:** Reject receipts without root lot (strict)
- **Warn:** Log exception but allow (current behavior)
- **Allow:** Silent pass (for non-critical items)

**Implementation:** See IMPLEMENTATION_GUIDE.md, Section 3

**Code Changes Required:**
- Add `missing_root_lot_behavior` field to Lot Trace Settings
- Update `subcontracting_receipt.before_submit()` (~15 lines)

**Risk:** Medium (changes error handling)

---

### 6. No Data Lifecycle Management

**Severity:** HIGH  
**Impact:** Stock Ledger Entries & Lot Exceptions grow unbounded, slowing queries after 2–3 years

**Current State:**
- No archival, purge, or retention policy
- Reports query all historical records
- 1000s of Stock Ledger Entries per lot per month accumulate

**Problem Scenario:**
- After 2 years: 50,000 lots × 100 entries per lot = 5M Stock Ledger Entries
- Root Lot Trace report becomes slow (full table scan)
- No way to clean up resolved exceptions

**Recommended Solution:**
Soft archival with scheduled job:
1. Monthly job marks completed lots (>12 months old) as archived
2. Reports filter WHERE is_archived = 0
3. Audit trail preserved (can un-archive anytime)

**Implementation:** See IMPLEMENTATION_GUIDE.md, Section 3

**Code Changes Required:**
- Add 3 custom fields: `is_archived` to Root Lot, Lot Exception, Stock Ledger Entry
- Create `archive_job.py` (~30 lines)
- Update reports (~5 lines each)
- Add settings to Lot Trace Settings

**Risk:** Low (disabled by default)

---

## 🟡 MEDIUM PRIORITY ISSUES

### 7. Lot Naming Rules – Hard-Coded per Product

**Severity:** MEDIUM  
**Impact:** Cannot reuse same yarn lot code for multiple products

**Current State:**
Each Lot Naming Rule tied to exactly one product:
```python
rule = frappe.db.get_value("Lot Naming Rule", {"product": product})
```

**Problem Scenario:**
- Acme Yarns supplies same greige yarn to multiple products
- Product A (Throw): uses EL/TH prefix
- Product B (Cushion): uses EL/CS prefix
- One purchase batch feeds both; must assign rule at PR time
- No intelligent fallback to default rule

**Recommended Solution:**
Add fallback chain in `find_naming_rule()`:
1. Try exact match: `yarn_item + product`
2. Fall back to: `yarn_item` only (default rule)
3. Return None if no match

**Implementation:** Update `find_naming_rule()` in common.py (~10 lines)

**Risk:** Low (backward compatible)

---

### 8. BOM Conversion – Missing Caching

**Severity:** MEDIUM  
**Impact:** Repeated BOM lookups during Subcontracting Receipt (N+1 queries)

**Current State:**
```python
def yarn_per_unit_from_bom(weaving_item, dyed_yarn_item=None):
    # Query executed every time, no caching
```

**Problem Scenario:**
- Subcontracting Receipt with 50 output items
- Each item calls `yarn_per_unit_from_bom()`
- Results in 50+ BOM queries (same BOM, same result)

**Recommended Solution:**
Add caching with 1-hour TTL:
```python
cache_key = f"lot_trace_bom_{weaving_item}_{dyed_yarn_item or 'any'}"
cached = frappe.cache().get(cache_key)
if cached is not None:
    return cached
# ... query ...
frappe.cache().set(cache_key, qty, expires_in_sec=3600)
```

**Implementation:** See IMPLEMENTATION_GUIDE.md, Section 1.7 or api/lot.py

**Code Changes Required:**
- Add cache get/set (~5 lines)
- Update function signature (+docstring)

**Risk:** Low (transparent improvement)

---

### 9. Lot Exception – No Auto-Resolve Rules

**Severity:** MEDIUM  
**Impact:** Audit log fills with info-level noise; Lot Manager must manually resolve

**Current State:**
```python
log_exception("Mixed Lots Override", "Info", ...)  # Created but not auto-closed
```

**Problem Scenario:**
- Every mixed lot override logs an exception
- Lot Exception list shows 100s of "Info" warnings
- Manager wastes time resolving non-critical entries

**Recommended Solution:**
Add auto-resolve rules based on severity:
- Info: auto-resolve after 1 hour if no action
- Warning: manual review (current behavior)
- Error: always require manual resolution

**Implementation:** Update `log_exception()` in common.py and Lot Exception doctype

**Code Changes Required:**
- Add `auto_resolve` parameter to `log_exception()` (~3 lines)
- Add scheduled job to auto-resolve expired Info exceptions (~15 lines)

**Risk:** Low (opt-in per exception type)

---

### 10. No Bulk Operations API

**Severity:** MEDIUM  
**Impact:** Cannot re-trace multiple lots at once; must reassign individually

**Current State:**
```python
def reassign_lot(root_lot, new_product):  # Single lot only
```

**Problem Scenario:**
- 50 lots need to be moved to new product category
- Must call `reassign_lot()` 50 times
- No batch API

**Recommended Solution:**
Add bulk operation:
```python
def bulk_reassign_lots(filter_dict, new_product):
    """
    Bulk update lots matching filters.
    filter_dict: {"product": "OLD_PRODUCT", "status": "Open"}
    """
    lots = frappe.get_all("Root Lot", filters=filter_dict, pluck="name")
    for lot_name in lots:
        reassign_lot(lot_name, new_product)
```

**Implementation:** Add to api/lot.py (~15 lines)

**Risk:** Low (new function, no breaking changes)

---

# SUMMARY TABLE

| Issue | Severity | Status | LOC | Risk | Phase |
|-------|----------|--------|-----|------|-------|
| No Optional Traceability | 🔴 CRITICAL | ❌ Open | 30 | Low | 1 |
| Weaver Balance No Customer Filter | 🔴 CRITICAL | ❌ Open | 10 | Low | 1 |
| UOM Conversion Failures | 🔴 CRITICAL | ✅ FIXED | — | — | — |
| Incomplete Mixing Policy | 🟠 HIGH | ❌ Open | 10 | Med | 2 |
| Missing Root Lot Silently Fails | 🟠 HIGH | ❌ Open | 15 | Med | 2 |
| No Data Lifecycle | 🟠 HIGH | ❌ Open | 50 | Low | 3 |
| Naming Rules per Product | 🟡 MEDIUM | ❌ Open | 10 | Low | 1 |
| BOM No Caching | 🟡 MEDIUM | ❌ Open | 5 | Low | 1 |
| Exception Auto-Resolve | 🟡 MEDIUM | ❌ Open | 20 | Low | 2 |
| No Bulk Operations | 🟡 MEDIUM | ❌ Open | 15 | Low | 3 |

---

# IMPLEMENTATION ROADMAP

## Phase 1: Selective Traceability (Week 1–2)
**Goal:** Make traceability optional per customer/item/supplier  
**Effort:** ~4 days  
**Risk:** Low

Tasks:
- [ ] Add custom fields: Customer.lot_trace_enabled, Item.lot_trace_enabled
- [ ] Extend Lot Naming Rule with apply_to_suppliers
- [ ] Update find_naming_rule() with supplier scope check
- [ ] Update purchase_receipt.before_submit() to skip non-traced items
- [ ] Update delivery.before_submit() to check customer flag
- [ ] Test: Trace one customer, skip another

**Success Criteria:**
- ✅ Yarn receipt with lot_trace_enabled=0 on Item → no root lot created
- ✅ Yarn receipt for non-whitelisted supplier → no root lot created
- ✅ Delivery for non-opted-in customer → no dispatch_type required

---

## Phase 2: Mixing Policy & Exception Handling (Week 3–4)
**Goal:** Configurable mixing policy + intelligent exception handling  
**Effort:** ~3 days  
**Risk:** Medium

Tasks:
- [ ] Add "Allow" mode to mixing_policy in Lot Trace Settings
- [ ] Update enforce_single_lot() with 3-mode logic
- [ ] Add allow_mixed_lots field to Stock Entry, Subcontracting Receipt
- [ ] Add missing_root_lot_behavior to Lot Trace Settings
- [ ] Update subcontracting_receipt.before_submit() to check setting
- [ ] Test each mode: Block, Warn, Allow

**Success Criteria:**
- ✅ Policy=Block + mixed lots → rejected
- ✅ Policy=Warn + mixed lots → allowed, logged
- ✅ Policy=Allow + mixed lots → allowed, silent

---

## Phase 3: Data Lifecycle & Performance (Week 5–6)
**Goal:** Archive old lots, improve report performance  
**Effort:** ~3 days  
**Risk:** Low

Tasks:
- [ ] Add is_archived custom field to Root Lot, Lot Exception
- [ ] Create archive_job.py with monthly scheduled job
- [ ] Update hooks.py with scheduled_jobs entry
- [ ] Update reports to filter WHERE is_archived=0
- [ ] Add archival settings to Lot Trace Settings
- [ ] Test: Verify archived lots not in reports

**Success Criteria:**
- ✅ Completed lot >12 months old → marked archived
- ✅ Root Lot Trace report excludes archived entries
- ✅ Archived lot can be un-archived by setting is_archived=0

---

# TESTING CHECKLIST

- [ ] **Selective Traceability:**
  - [ ] Purchase: Item with lot_trace_enabled=0 → no lot created
  - [ ] Purchase: Supplier not in apply_to_suppliers → no lot created
  - [ ] Delivery: Customer with lot_trace_enabled=0 → no dispatch_type required
  - [ ] Delivery: Customer with lot_trace_enabled=1 → dispatch_type required

- [ ] **Mixing Policy:**
  - [ ] Policy=Block: Two lots in one SE → error
  - [ ] Policy=Block + allow_mixed_lots=1 + Lot Manager → allowed, logged
  - [ ] Policy=Warn: Two lots in one SE → allowed, logged
  - [ ] Policy=Allow: Two lots in one SE → allowed, silent

- [ ] **Data Archival:**
  - [ ] Root Lot >12 months, status=Completed → archived (is_archived=1)
  - [ ] Root Lot <12 months → not archived
  - [ ] Archived lot still visible in Root Lot list but filtered in reports
  - [ ] Un-archive: set is_archived=0 → lot reappears in reports

- [ ] **Performance:**
  - [ ] Root Lot Trace report <2s for 1000-entry lot
  - [ ] BOM queries cached (verify cache hits in logs)
  - [ ] At-Weaver Balance <1s for 100 lots

---

# DEPLOYMENT NOTES

**Backward Compatibility:**
- ✅ All changes are additive (no breaking changes to existing code paths)
- ✅ New fields default to "off" (preserve current behavior)
- ✅ Old lots continue to work without migration

**Migration Required:**
None. Changes work on all existing data.

**Rollback Plan:**
1. Phase 1 (Selective Traceability): Set all lot_trace_enabled=1 → reverts to current behavior
2. Phase 2 (Mixing Policy): Set mixing_policy=Block → reverts to current behavior
3. Phase 3 (Archival): Set enable_auto_archival=0 → disables archival

---

# REFERENCES

- **IMPLEMENTATION_GUIDE.md** – Step-by-step implementation with code examples
- **lot_trace/api/lot.py** – Core API functions (fixed UOM conversion)
- **lot_trace/events/common.py** – Shared helpers (add custom find_naming_rule, enforce_single_lot)
- **lot_trace/hooks.py** – Add scheduled_jobs entry

