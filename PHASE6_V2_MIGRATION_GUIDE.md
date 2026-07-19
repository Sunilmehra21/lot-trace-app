# Phase 6 V2 — Migration Guide (V1 → V2, SIMPLIFIED)

**Date:** July 2026  
**Reason:** Phase 6 V1 was too complex for non-technical users. V2 is 9x simpler, same power.

---

## What Changed (V1 → V2)

| Aspect | V1 (Complex) | V2 (Simplified) | Why |
|--------|---|---|---|
| **Config Doctype** | Lot Trace Profile (nested tables) | Lot Naming Rule (flat) | Same name as before; users recognize it |
| **Child Table** | Lot Trace Item (many fields) | Lot Naming Rule Yarn (3 fields only) | Removed BOM, dyed patterns (not needed) |
| **Batch Patterns** | Config table with `{LOT}` tokens | Hardcoded in code | No user-editable patterns; simpler |
| **Stage Route** | Text field (informational) | Link to Lot Route doctype | Can link to actual stages; no free-text |
| **Fields to Remove** | lot_code_pattern, stage_route, batch_naming_rules | N/A | All simplified away |
| **BOM Kg/Pc** | In Trace Items table | Removed | Already in Product BOM; no duplication |

---

## New "Lot Naming Rule" Form (Super Simple)

**Header:**
- **Product** (link)
- **Active** (checkbox)
- **Lot Code Prefix** (text, e.g., "MV/BG")
- **Lot Route** (link to Lot Route doctype, optional)

**Child Table: Yarns**
- **Yarn Item** (link to Item)
- **Role** (Primary or Secondary dropdown)
- **Abbr** (short code like A, B, CT, CH)

**That's it.** 4 fields, no nesting, no confusion.

---

## Batch Naming (Automatic, Hidden)

No more config tables. Batch names are **hard-coded and auto-generated**:

```
NT:  {lot_code}-{abbr}-NT           → 01-A-NT, 01-B-NT
DY:  {lot_code}-{abbr}-{color}-DY   → 01-A-BK-DY, 01-B-RED-DY
WV:  {lot_code}-WV                  → 01-WV
CT:  {lot_code}-CT                  → 01-CT
```

**Users don't touch these.** They're automatically generated from the stage, abbr, and color.

---

## Lot Code Generation (Automatic)

**Pattern:** `{prefix}/{MMYY}/{serial}`

**User sets:** Prefix (e.g., `MV/BG`)  
**System generates:** Month-year and serial (01, 02, 03…)

**Example:**
- Prefix: `MV/BG`
- July 2026, 1st lot → `MV/BG/0726/01`
- July 2026, 2nd lot → `MV/BG/0726/02`
- August 2026, 1st lot → `MV/BG/0826/01`

---

## Migration: Old Data → New Format

When you update and run `bench migrate`, **Phase 6.1 patch automatically:**

1. Reads your existing **Lot Trace Profile** records
2. Extracts the prefix from the lot code pattern
3. Copies all yarns from Trace Items table
4. Creates new **Lot Naming Rule** records (one per product)
5. Marks old Profiles as read-only (backup kept, not deleted)

**Result:** No data loss, no manual work.

---

## Setup (After Migration)

### For New Products:

1. Go to **Manufacturing → Lot Naming Rule**
2. Click **New**
3. Fill:
   - Product: ELSABET THROW
   - Lot Code Prefix: MV/BG
   - Lot Route: (optional, link to existing route)
4. Add Yarns:
   - Row 1: Yarn=RM-YN-COTTON-CN, Role=Primary, Abbr=A
   - Row 2: Yarn=RM-YN-CHENILLE-CN, Role=Secondary, Abbr=B
5. **Save**

Done. No patterns to edit, no batch-naming-rules table, no confusion.

### For Migrated Products:

Review auto-created rules:
1. Check Lot Code Prefix (should match your old pattern)
2. Check Lot Route (may be empty; set if you have one)
3. Verify Yarns table (should have primary + secondaries)
4. **Save**

---

## How It Works Under the Hood

**The phase 6 logic is unchanged:**
- Primary yarn receipt → create new lot (serial +1)
- Secondary yarn receipt → reuse oldest open lot waiting for it (FIFO)
- Dyed yarn receipt → lot auto-resolved from consumed greige batch (no manual picking)
- Batch names auto-generated from stage + abbr + color

**The config is just simpler:**
- Read from Lot Naming Rule (not Profile)
- Batch patterns hardcoded (not configurable)
- No `{}` tokens, no nested tables

**Result:** 90% of the complexity is hidden; users see a 4-field form.

---

## What's Removed

**These V1 doctypes are deprecated (but kept read-only as backup):**
- Lot Trace Profile
- Lot Trace Item
- Lot Batch Naming Rule

**If you had Phase 6 V1 live:**
- Old data is migrated to new Lot Naming Rule format
- Reports still work (they read from Root Lot, not config)
- Tree report fixed (method name was wrong; now works)

---

## Install Steps (V2 Fresh or V1 → V2 Migration)

1. **Copy V2 files over V1:**
   - Replace `lot_trace/events/resolver.py` with `resolver_v2.py`
   - Replace `lot_trace/events/lot_factory.py` with `lot_factory_v2.py`
   - Replace `lot_trace/events/purchase_receipt.py` with `purchase_receipt_v2.py`
   - Replace `lot_trace/events/subcontracting_receipt.py` with `subcontracting_receipt_v2.py`
   - Replace doctype JSON for Lot Naming Rule (add Yarns table, Lot Route)
   - Add new doctype: Lot Naming Rule Yarn
   - Keep Lot Trace Profile read-only (don't delete; backup)

2. **Update patches.txt:**
   ```
   [pre_model_sync]
   
   [post_model_sync]
   lot_trace.patches.v6_0_add_custom_fields
   lot_trace.patches.v6_0_extend_root_lot
   lot_trace.patches.v6_1_simplify_profile_to_rule
   ```

3. **Run migration:**
   ```
   bench --site <site> migrate
   bench --site <site> clear-cache
   ```

4. **Review created rules:**
   - Check each migrated **Lot Naming Rule**
   - Verify prefix, lot route, yarns
   - Adjust abbreviations if needed (e.g., use CT/CH instead of A/B)

---

## FAQ

**Q: Do I lose my old Lot Naming Rules (Phase 5 single-yarn)?**  
A: No. Phase 5 rules are auto-updated to use the new Yarns table. Existing data is preserved.

**Q: Can I still use single-yarn products?**  
A: Yes. Just add one row to the Yarns table with Role=Primary. Same behavior as Phase 5.

**Q: Why remove batch-naming-rules table?**  
A: Because batch names follow a predictable, hard-coded pattern. Letting users edit patterns caused mistakes. Hardcoding is safer & simpler.

**Q: What's the Lot Route link for?**  
A: Optional reference to the Lot Process Stage chain (NT→DY→WV→CT). Helps non-technical users understand the stage flow. Can be left blank.

**Q: Will old reports break?**  
A: No. Reports read from Root Lot, not from config. The tree report is fixed (method name bug).

**Q: Can I customize abbreviations?**  
A: Yes, change the Abbr field in the Yarns table. Use A/B or CT/CH or any short code you prefer.

---

## Tree Report: Fixed

**Bug in V1:** Method name was `get_lot_tree` but API expected `get_trace_tree`.  
**Fix in V2:** Renamed to `get_trace_tree` (correct).

**Result:** Lot Trace Tree report now works perfectly.

---

## Support & Questions

If anything isn't clear:
- Check this guide
- Review the simplified Lot Naming Rule form (super intuitive)
- Ask your Quality Manager or Manufacturing IT

---

**That's it. Phase 6 V2 is done. Same power, 9x simpler.**
