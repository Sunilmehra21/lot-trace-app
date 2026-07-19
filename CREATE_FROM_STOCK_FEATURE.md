# Create Root Lot from Stock — Phase 4 A.4 Implementation

**Status:** Complete  
**Files Added:**
- `lot_trace/api/create_from_stock.py` — Backend API
- `lot_trace/public/js/root_lot_list.js` — List view button + dialog

---

## Use Case

**Phase 4 Question A.4:** "What if, instead of purchasing natural yarn for the first stage, we used yarn from our existing stock?"

**Answer:** Create a Root Lot manually from existing warehouse inventory. Useful for:
- Starting lot traceability with old stock
- Internal transfers from one department to another
- Stock-take scenarios where existing inventory needs traceability
- Simulating a lot flow without a purchase receipt

---

## How It Works

### User Workflow

1. Open Root Lot list view
2. Click **"Create from Stock"** button (top-right action menu)
3. Dialog opens:
   - **Item:** Select yarn/fabric item
   - **Warehouse:** Select warehouse where item is stored
   - **Quantity:** Amount to allocate (checked against available stock)
   - **Product (optional):** If set, override product from Lot Naming Rule
4. Click **"Create Lot"**
5. System:
   - Validates item, warehouse, quantity
   - Looks up Lot Naming Rule for the item (required)
   - Generates Root Lot code (date-based as usual)
   - Creates Root Lot doc
   - Creates Birth Stage Batch (NT by default, or per rule)
   - Creates Stock Entry (Material Issue) to deduct qty from warehouse
   - Navigates to new Root Lot form

### The Repack Approach (Why Not Material Issue?)

**Repack (Correct):**
```
INPUT:  15,000 kg RM-YN-BCI-CN in Weaving - WIP warehouse (unassigned batch)
REPACK: Issue from warehouse → Receive to warehouse (same warehouse, different batch)
OUTPUT: 15,000 kg RM-YN-BCI-CN in batch MV/BG/0726/01-NT

Result: Warehouse balance = 15,000 kg (unchanged)
        Item now linked to new batch (lot)
        Audit trail: 1 Repack transaction
```

**Material Issue (Incorrect):**
```
INPUT:  15,000 kg in warehouse
ISSUE:  Deduct from warehouse (no target warehouse)
OUTPUT: Balance = 0 kg (wrong! item physically in warehouse)

Result: Warehouse balance = 0 kg (misleading)
        Would need Material Receipt to restore balance (2 transactions, messy)
        Semantically wrong: suggests item was consumed/used
```

**Why Repack is better:**
- ✅ Single transaction
- ✅ Warehouse balance stays correct (15,000 kg)
- ✅ Semantically clear: "reassign batch, not consume"
- ✅ No follow-up transactions needed
- ✅ Item immediately ready for traceability

### Backend: `create_from_stock.py`

```python
create_root_lot_from_stock(item_code, warehouse, qty, product=None)
```

**Validation:**
- Item exists in master
- Warehouse exists
- Quantity > 0
- Quantity ≤ available stock in warehouse
- Lot Naming Rule exists for the item

**Creation:**
1. Root Lot doc with:
   - lot_code (auto-generated from rule)
   - product, yarn_item, received_qty, uom, current_stage
   - custom_created_from_stock = True (for audit trail)
   - supplier = "Internal Stock"

2. Batch doc (birth stage, e.g., NT-DY)

3. Stock Entry (Material Issue):
   - Deducts qty from warehouse
   - Links to batch
   - Submits automatically
   - Creates Stock Ledger Entry

**Return:**
```json
{
  "root_lot": "MV/BG/0726/01",
  "batch": "MV/BG/0726/01-NT",
  "item": "RM-YN-...",
  "qty": 15000.0,
  "warehouse": "Weaving - WIP",
  "stock_entry": "SE-2026-00123",
  "message": "Root Lot ... created from stock. Stock Entry ... submitted."
}
```

---

## Key Design Decisions

1. **Stock Entry Type: Repack (Not Material Issue)** ✅
   - **Why Repack?** It reassigns qty to a new batch WITHOUT changing warehouse balance
   - Semantic meaning: "This yarn is now tracked under a new lot"
   - Physical inventory unchanged, just linked to new batch
   - Single transaction (no follow-up needed)
   - **Why NOT Material Issue?** Would deduct qty from warehouse (balance = 0), misleading since yarn is physically still there

2. **Lot Naming Rule is mandatory** — ensures consistent lot codes even for stock-created lots

3. **Stock Entry is auto-created** — not optional. This:
   - Keeps inventory balance correct
   - Creates audit trail (who, when, why reassigned)
   - Links batch to Stock Ledger (traceability works end-to-end)

4. **custom_created_from_stock = True** — marker field for reporting/audits

5. **Supplier = "Internal Stock"** — distinguishes from purchased lots

6. **First stage (birth) is per rule** — respects the product's defined flow (NT vs DY start)

---

## Stock Entry Type Decision: Repack vs Material Issue

**IMPORTANT:** Phase 5 initially used Material Issue (wrong), now corrected to Repack (right).

See `REPACK_vs_MATERIAL_ISSUE.md` for full comparison and why Repack is correct.

**Summary:**
- **Repack:** Reassigns qty to new batch, warehouse balance unchanged, 1 transaction ✅
- **Material Issue:** Deducts qty as consumed, balance = 0 (wrong), needs 2 transactions ❌

---

## Testing Checklist

- [ ] Navigate to Root Lot list, find "Create from Stock" button
- [ ] Click button, dialog appears with 4 fields
- [ ] Select item: list shows only items in master
- [ ] Select warehouse: list shows active warehouses
- [ ] Enter qty > available stock: error "Insufficient stock"
- [ ] Enter qty ≤ available: validation passes
- [ ] Select item with NO Lot Naming Rule: error "No rule found"
- [ ] Submit dialog: Root Lot created, navigates to form
- [ ] Check Stock Entry: Material Issue, qty deducted, batch linked
- [ ] Check Batch: birth stage (NT or per rule), batch_no correct
- [ ] Run Lot Trace Tree: shows birth stage with 0 balance (issued out)
- [ ] Run Root Lot Trace: shows -qty transaction (Material Issue)

---

## Integration with Phase 5

- Uses same `find_naming_rule()`, `first_stage_for_rule()`, `make_lot_code()` from common.py
- Compatible with color_abbr_for_item() (batch naming is per-stage rules)
- Integrates with Lot Trace Tree (stock entry shows as inbound movement)
- integrates with Root Lot Trace report (Material Issue appears in ledger)

---

## Edge Cases

| Scenario | Behavior |
|----------|----------|
| Item has no Lot Naming Rule | Error: "No rule found" |
| Warehouse doesn't exist | Error: "Warehouse not found" |
| Stock qty < requested qty | Error: "Insufficient stock" |
| Qty = 0 or negative | Error: "Qty must be > 0" |
| Item in multiple warehouses | User picks one warehouse at a time |
| Lot Naming Rule inactive | Uses active rule only (find_naming_rule filters) |
| Product field in dialog omitted | Uses product from Lot Naming Rule |

---

## Optional Enhancements (Future)

1. **Batch upload:** CSV import for bulk "Create from Stock" (for stock-take recovery)
2. **Stock deduction mode:** Option to NOT auto-create Stock Entry (for report-only scenarios)
3. **Reason field:** Allow user to enter reason for stock-to-lot conversion (audit trail)
4. **Multi-item:** Create lot from multiple items' stock in one dialog (for blended products)

---

## Files Summary

| File | Purpose | Lines |
|------|---------|-------|
| `lot_trace/api/create_from_stock.py` | API method, validation, Root Lot + Batch + Stock Entry creation | 100 |
| `lot_trace/public/js/root_lot_list.js` | List button, dialog form, API call, navigation | 60 |

**Total:** ~160 lines for Phase 4 A.4 completion.

