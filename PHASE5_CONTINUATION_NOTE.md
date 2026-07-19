# Phase 5 — Continuation Note (Multi-Color Multi-Yarn Traceability)

**Status:** Files created, not yet deployed/tested  
**Date:** July 2026

---

## Objective

Fix 6 critical issues discovered during Phase 4 testing around multi-color and multi-yarn products:
- **B2:** DY batch naming inconsistent (`…-DY` vs `…-DY-RM_YN_BC`)
- **B3:** Lot Consumption table manual entry + wrong summed validation
- **B4:** Multi-color DY shown nested + loss calculated wrong
- **B5:** Root Lot Trace balance = warehouse total, not batch-specific
- **B6:** Weaved pcs shows 0, status "Completed" when actually in-progress
- **A1:** No documented setup for multi-yarn products (Phase 5 design patterns)

---

## Design Decisions (Phase 5)

### 1. Color-Code DY Batch Naming (B2 Fix)
**File:** `common.py` → `color_abbr_for_item()` + `batch_id_for_stage()`
- DY batches now named `{root_lot}-{COLOR_ABBR}-DY` (e.g. `MV/BG/0726/01-BK-DY`)
- Color sourced from: Item Colour attribute abbr → item code segment → 4-char fallback
- Non-DY stages keep classic suffix `{root_lot}-{suffix}`
- **Result:** `MV/BG/0726/01-BK-DY` and `MV/BG/0726/01-WH-DY` are equal-pattern siblings

### 2. BOM-Auto Lot Consumption (B3 Fix)
**File:** `purchase_receipt.py` → `handle_multi_lot_weaving()` + `allocate_weaving_consumption()`
- **User no longer types qty_kg** — it's auto-calculated from BOM per dyed-yarn-item
- Lot Consumption table rows: just `{root_lot}` + optional `{dyed_yarn_item}` for display
- `qty_kg` auto-fills by allocating BOM requirement lot-by-lot (primary first)
- **Per-item validation:** each yarn item in BOM validated separately (color A can't cover color B)
- Tolerance: `weaving_tolerance_pct` (Settings, default 2%) — allows ±2% or 0.5 kg per item
- **Benefit:** User never calculates, fewer data-entry errors

### 3. Multi-Color DY as Siblings (B4 Fix)
**File:** `tree.py` → stage-level grouping + loss group-to-group
- Batches of same stage are SIBLINGS (not nested), e.g. `…-BK-DY` and `…-WH-DY` both at DY level
- Stage node = aggregated totals (sum in_qty, sum out_qty, sum balance) of all batches
- Loss % = `(NT-consumed − DY-in) / NT-consumed` (both aggregated, not batch-by-batch)
- Side panel sums all DY batches together (not listed as sub-stages)
- **Result:** 14,962 kg NT consumed vs 14,250 kg DY in (both colors) = 4.76% loss ✓ (not 52%)

### 4. Per-Batch Running Balance (B5 Fix)
**File:** `root_lot_trace.py` (Root Lot Trace report)
- Balance computed PER BATCH cumulatively, not using `qty_after_transaction`
- `batch_balance[batch_no]` tracked independently
- Result: balance reflects this batch's qty in warehouse, not item-warehouse total
- **Example:** `MV/BG/0726/01-BK-DY` balance 7,147 Kg ≠ item RM-YN-BCI-DYE-BK-CN total in warehouse

### 5. Weaved Pcs from Net In-Qty + Effective Status (B6 Fix)
**Files:** `order_lot_overview.py` (report) + `lot.py` (`remaining_yarn_kg()`, `effective_status()`)
- **Weaved pcs = netted `in_qty` of WV batch** (what actually entered weaving), not balance
- Status logic:
  - Greige phase: "Open" → "In Progress" once received
  - Dyed phase: remains "In Progress" while DY balance > 1 kg (tolerance)
  - Weaving phase: "Completed" only when DY consumed ≤ 1 kg AND weaving produced pcs
  - **Fallback:** check `remaining_yarn_kg()` = stock NT/DY + at-weaver balances; if > 10 kg or > 0.5% of received, override to "In Process"

### 6. Multi-Yarn Product Setup (A1 Documentation)
**One rule per yarn item:**
- Product ELSABET THROW uses cotton + chenille → TWO Lot Naming Rules (both active, same product)
- Each yarn receipt → separate Root Lot (001, 002, ...)
- BOM for final good lists both yarn items with their kg/pc
- At weaving: Lot Consumption table auto-allocates from both lots per BOM
- **Result:** Two lots merge cleanly at weaving with full traceability

---

## Files Created (Phase 5 + Phase 4 A.4)

| Path | Purpose | Key Changes |
|------|---------|------------|
| `lot_trace/api/lot.py` | Lot APIs | `color_abbr_for_item()`, `dyed_available_map()` (per-item), `dyed_requirements_from_bom()`, `allocate_weaving_consumption()`, `effective_status()`, `remaining_yarn_kg()` |
| `lot_trace/events/common.py` | Helpers | `color_abbr_for_item()`, `batch_id_for_stage()` (color-coded DY), `weaving_tolerance_pct()` |
| `lot_trace/events/purchase_receipt.py` | Receipt handler | `handle_multi_lot_weaving()` (BOM-auto, per-item validation), `_validate_aggregate_single_lot()` (fallback) |
| `lot_trace/api/tree.py` | Tree data API | Stage-level grouping, group-to-group loss, sub_batches array (multi-DY display) |
| `lot_trace/lot_trace/report/root_lot_trace/root_lot_trace.py` | Report | Per-batch running balance (B5 fix) |
| `lot_trace/lot_trace/report/order_lot_overview/order_lot_overview.py` | Report | Weaved = netted in_qty (B6 fix), effective_status() logic |
| `lot_trace/api/create_from_stock.py` | **[NEW]** Create lot from stock | API to create Root Lot + Batch + Stock Entry from existing warehouse inventory (Phase 4 A.4) |
| `lot_trace/public/js/root_lot_list.js` | **[NEW]** List UI | "Create from Stock" button, dialog form, user workflow |

**Location:** `/phase5/lot_trace/` folder (ready to copy over repo)

---

## Key Code References

### Color Extraction Chain (common.py)
```python
def color_abbr_for_item(item_code):
    # 1. Item Colour attribute abbr (from Item Variant Attribute)
    # 2. Extract from item code (e.g. …-BK-CN → BK)
    # 3. Fallback: first 4 chars of scrubbed code
```

### DY Batch ID Pattern
```python
def batch_id_for_stage(root_lot, stage_code, item_code):
    if stage_code == "DY":
        return f"{root_lot}-{color_abbr_for_item(item_code)}-DY"
    else:
        return f"{root_lot}-{stage_suffix}"
```

### BOM-Auto Allocation (purchase_receipt.py)
```python
reqs = dyed_requirements_from_bom(weaved_item, pcs)  # {item: kg_needed}
avail = {lot: dyed_available_map(lot, supplier) for lot in lots}  # per-item map
# allocate lot-by-lot, respecting per-item limits
```

### Effective Status Check (lot.py)
```python
def effective_status(root_lot, stored_status, received_qty=0):
    if stored_status != "Completed":
        return stored_status
    threshold = max(10.0, received_qty * 0.005)
    if remaining_yarn_kg(root_lot) > threshold:
        return "In Process"
    return "Completed"
```

---

## Testing Checklist (Pending)

- [ ] Multi-color DY receipt (2 colors, same lot) — verify batches `…-BK-DY` and `…-WH-DY` created
- [ ] Lot Trace Tree DY node aggregates both colors + loss = 4.76% ✓
- [ ] Lot Consumption table auto-fills qty_kg from BOM (2 yarn items)
- [ ] Root Lot Trace report balance per-batch (not warehouse total)
- [ ] Order Lot Overview weaved_pcs = 400 (in_qty), not 0 (balance)
- [ ] Order Lot Overview status = "In Process" (1,800 pcs manufactured, 5,344 needed)
- [ ] Per-item validation: color A shortage blocked (not covered by color B)
- [ ] Weaving tolerance 2% + 0.5 kg threshold tested
- [ ] Multi-yarn (cotton + chenille) full lifecycle test

---

## Phase 4 A.4: Create Lot from Stock (NOW ADDED)

**Feature:** "Create Root Lot from Stock" button on Root Lot list

**Files Added:**
- `lot_trace/api/create_from_stock.py` — API method, validation, Root Lot + Batch + Stock Entry creation
- `lot_trace/public/js/root_lot_list.js` — List button, dialog, user workflow
- `CREATE_FROM_STOCK_FEATURE.md` — Full feature documentation

**Addresses Phase 4 A.4:** "What if we use yarn from existing stock?"

**How It Works:**
1. Click "Create from Stock" button on Root Lot list
2. Dialog: select Item, Warehouse, Qty, optional Product
3. System validates stock availability, looks up Lot Naming Rule
4. Creates Root Lot + Birth Batch + Stock Entry (Material Issue)
5. Navigates to new Root Lot form

**Key Design:**
- Stock Entry auto-created (maintains inventory accuracy + audit trail)
- Lot Naming Rule is mandatory (consistent lot codes)
- custom_created_from_stock = True (marker field)
- Supplier = "Internal Stock" (distinguishes from purchased)

---

## Unresolved / Optional Enhancements

1. **Auto-fill Lot Consumption from SO?** Currently manual; could pre-populate from SO line item's root_lot if SO is linked to PR.
2. **Colour attribute abbreviation fallback:** Currently item-code segment extraction; may need customer-specific mapping if abbreviations inconsistent.
3. **Weaving tolerance setting:** Hardcoded 2% default in Phase 5; could be moved to Lot Trace Settings for per-firm customization.
4. **At-Weaver Balance report filters:** Phase 4 had supplier filter working; Phase 5 `dyed_available_map()` maintains per-item map but report still using old single-valued map — may need UI update to show per-item balances.

---

## Deployment Steps

1. Copy `/phase5/lot_trace/` over repo at same paths.
2. Commit + push.
3. Frappe Cloud: Fetch Latest → **Migrate** (new Lot Trace Settings field: `weaving_tolerance_pct`).
4. Clear cache + hard-refresh browser.
5. Run Phase 5 test checklist.

---

## Known Issues (Still Open)

- None; all 6 issues (B2–B6, A1) addressed in Phase 5 files.

---

## Important Numbers / Settings

| Setting | Value | Notes |
|---------|-------|-------|
| DY Batch Name Pattern | `{lot}-{COLOR}-DY` | Phase 5 standard for multi-color |
| Weaving Tolerance | 2% or 0.5 kg | Per BOM item, default in code; moveable to Settings |
| Consumed Tolerance (Status) | 1.0 kg | DY balance threshold before marking "Completed" |
| Remaining Yarn Threshold | 10 kg or 0.5% of received | Triggers "In Process" override (effective_status) |

---

## Next Session: Start Here

1. Read Phase 5 files (especially `purchase_receipt.py` for BOM-auto logic).
2. Deploy Phase 5 to test site.
3. Run test checklist (multi-color DY, auto-Lot Consumption, per-batch balance, effective status).
4. If all pass → document Phase 5 in updated SOP.
5. If issues → debug with test data from the screenshots (lot MV/BG/0726/01).

