# Phase 4 — Answers, Bug Fixes & Implementation Plan

**Date:** July 2026

Phase 4 has two parts:
- **Part A** — answers to your 4 process questions (with the features that make them work)
- **Part B** — fixes for the 5 known issues

All changed files are complete replacements in this `phase4/` folder. Copy them over your repo files at the same paths (see "Deployment" at the end).

---

## Part A — Your 4 Questions Answered

### Q1. Multi-color dyed yarn — one product made from SEVERAL yarns

**How it works now (no code change needed for the main flow):**

There are actually two different scenarios, and the module already handles both:

**Scenario A — one greige yarn, dyed into MULTIPLE colors:**
- One yarn receipt → one Root Lot (e.g. `MV/TH/0726/001`).
- You send the NT yarn to the dyer in portions and receive back e.g. Beige and Black as DIFFERENT dyed items on separate Subcontracting Receipts.
- `create_stage_batch()` already handles this: the first color gets batch `MV/TH/0726/001-DY`; when a second dyed ITEM arrives for the same lot, it automatically gets an item-suffixed batch: `MV/TH/0726/001-DY-2_6S_COTT…`.
- Both DY batches belong to the same Root Lot, so the trace tree shows both colors under one lot. **This was already supported — I've added a comment in `common.py` clarifying it's the designed behaviour, not a collision fallback.**

**Scenario B — DIFFERENT greige yarns (e.g. cotton + chenille) into one product:**
- Create **one Lot Naming Rule per yarn item** — they can share the same Product and even the same prefix. `find_naming_rule()` matches on yarn_item, so each yarn receipt births its OWN root lot (001 = cotton, 002 = chenille).
- The lots then meet at weaving via the **Lot Consumption (multi-lot weaving) table**: the weaving PR lists both lots and the kg consumed from each. The primary lot drives the FG lot number; the other lot is audit-trailed as "merged".
- So Case 2 (built in Phase 3C) IS the multi-yarn mechanism — it is not only for same-yarn blending.

**Setup checklist for a multi-yarn product:**
1. One Lot Naming Rule per yarn item (same product allowed).
2. The weaved item's BOM lists ALL its yarn inputs (each dyed yarn with its kg per pc).
3. On the weaving PR, fill the Lot Consumption table with every source lot.

### Q2. Which route / lot / batch when weaved pcs come back

The receiving process for weaved pcs is:

1. **Purchase Order** to the weaver with `Lot Stage = WV` — that's what flags the PR rows as weaving receipts (`is_weaving_row()`).
2. **Purchase Receipt** against that PO:
   - **Root Lot on the item row** = the PRIMARY lot whose yarn was woven. **Phase 4 fix:** this dropdown is now filtered to show ONLY lots whose dyed yarn was actually sold to this supplier (see Part B #2) — with the sold kg shown next to each lot.
   - **Route** — you never pick a route on the PR. The route was fixed at lot birth (copied from the Lot Naming Rule onto the Root Lot). The receipt validates against it automatically (`create_stage_batch()` route guard).
   - **Batch** — never typed by hand. The system creates/links `{root_lot}-WV` automatically on submit.
   - **Multi-lot?** Fill the Lot Consumption table; the primary lot must be one of its rows.
3. On submit the system validates pcs qty vs dyed yarn available with that weaver (BOM conversion), creates the `-WV` batch, and advances the lot stage.

So the only manual decision is "which root lot(s)" — and that list is now pre-filtered to the correct answer.

### Q3. Starting directly with FABRIC (no greige yarn stage)

**New in Phase 4 — route-aware lot birth:**

Previously lot birth was hardcoded to stage NT. Now:

1. Create a **Lot Route** that starts at the real first stage, e.g. `WV → CT → ST → FN → PK → FG` (or add a dedicated `FB · Fabric` Lot Process Stage and route `FB → CT → …`).
2. Attach that route to the **Lot Naming Rule** for the fabric item.
3. When the fabric Purchase Receipt is submitted, `first_stage_for_rule()` reads the route's first stage and the lot is born there: batch `{lot}-WV` (or `-FB`), current stage = WV/FB. No NT/DY batches ever exist for that lot.
4. The Trace Tree progress bar (also fixed in Phase 4) uses the lot's planned route, so a fabric lot shows progress out of ITS stages only.

`on_cancel` was also updated: it now checks downstream batches relative to the lot's **birth stage** (was hardcoded NT), so cancelling a fabric receipt cleans up correctly.

### Q4. Using yarn from EXISTING stock (not a fresh purchase)

**New in Phase 4 — `create_lot_from_stock()` API (Lot Manager only):**

Lot birth only hooked Purchase Receipts before. For stock already in the warehouse (bought before the module, or bought untraced), call:

```
POST lot_trace.api.lot.create_lot_from_stock
args: item_code, qty, warehouse, product (optional), posting_date (optional)
```

What it does:
1. Finds the Lot Naming Rule (same selective-traceability checks as a purchase).
2. Creates the Root Lot (supplier = blank, audit comment "created from existing stock by <user>") + the first-stage batch.
3. Creates a **DRAFT Repack Stock Entry** that consumes the un-batched stock and produces the same qty INTO the new lot batch.
4. You review and submit that Stock Entry — from then on the lot behaves exactly like a purchased one (dyeing, weaving, reports, tree, flow chart all work).

Recommended UI: add a "Create Lot from Stock" button on the Root Lot list (client script calling this method). I can add that in the next iteration if you want it one-click.

---

## Part B — The 5 Known Issues, Fixed

### B1. At-Weaver Balance: weaver filter not working ✅

**Root cause:** the filter field is a **Supplier** link, but the report rows carry **Customer** names (dyed yarn is sold via DN/SI to the weaver's customer record). `if weaver != weaver_name` compared a supplier name to a customer name → never matched → empty report.

**Fix (`api/lot.py`):** new helper `customers_for_supplier(supplier)` resolves the supplier to its customer record(s) via `Customer.represents_supplier` + the same-name assumption. The filter now matches through that mapping, and the reverse lookup (customer → supplier for the pcs PR query) uses `represents_supplier` too instead of assuming same name. Works with or without the Root Lot filter.

### B2. PR Root Lot dropdown shows ALL lots ✅

**Fix:** new whitelisted link query `weaver_root_lot_query` (`api/lot.py`) + client script `public/js/purchase_receipt.js`. The Root Lot fields (item row AND Lot Consumption table) now list only lots whose **dyed yarn was sold (DN/SI) to this PR's supplier**, showing "X kg dyed sold" next to each lot. Falls back to all lots when the supplier has no customer mapping.

*(Note: you said "sales invoice to the same customer" — the query covers both Delivery Note and Sales Invoice issues.)*

### B3. Lot Consumption table: item filter + available qty ✅

**Fixes:**
- `dyed_item_query` (`api/lot.py`): the Dyed Yarn Item dropdown now lists only the DY-batch items of the selected root lot.
- New read-only column **"Available with Weaver (Kg)"** on Lot Consumption Detail (`lot_consumption_detail.json` — re-migrate to add the column).
- `get_dyed_available()` (`api/lot.py`): live availability = dyed kg sold to this weaver **minus** kg already consumed by earlier weaving PRs (both multi-lot rows and single-lot BOM equivalents). Picking a lot in the table auto-fills the dyed item, fills Available Kg, and shows a green/orange alert; entering a qty above availability shows a red warning immediately.
- Server-side (`events/purchase_receipt.py`): the multi-lot validation now checks against **remaining availability** (was: total sold — so a second PR could double-consume the same yarn; that's also fixed).

### B4. Trace Tree: progress bar 100% too early + one color for CT/ST/EM/FN/PK ✅

**Progress root cause:** the old formula divided *active batches / created batches* — an incomplete chain (4 batches, all active) = 4/4 = 100%.

**Fix:** `api/tree.py` now returns `planned_stages` (the lot's Lot Route, or all active global stages when no route). The page computes **stages reached / planned stages** — your screenshot's lot now shows 4 of 8 = 50%, with pending stages listed greyed-out ("pending —") in the Stage Progress panel. When FG exists, the label also appends "% of FG dispatched".

**Legend colors:** every stage now has its own chip color (`lot_trace_tree.css` + `stage_class()`): NT purple, DY blue, WV teal, **CT orange, ST amber, EM violet, FN green, PK brown**, FG pink. The legend shows 9 separate chips instead of one combined "CT/ST/EM/FN/PK".

### B5. Flow Chart: "+3" doesn't show the other transactions ✅

**Root cause:** the API only sent `first_voucher` + a count; the page had nothing to open.

**Fix:** `api/flow.py` now returns the **full voucher list** per cell (voucher no, type, net qty, date). In `lot_flow.js` the "+N" is now its own clickable link that opens a dialog listing ALL transactions of that stage — each row opens its document, with type, +/− qty (green/red) and date. The first voucher still opens directly like before.

---

## Files Changed in Phase 4

| File | Change |
|---|---|
| `lot_trace/api/lot.py` | B1 weaver filter fix; `customers_for_supplier`, `get_dyed_available`, `weaver_root_lot_query`, `dyed_item_query`, `create_lot_from_stock` (Q4) |
| `lot_trace/api/tree.py` | B4: returns `planned_stages` for true progress |
| `lot_trace/api/flow.py` | B5: returns full voucher list per cell |
| `lot_trace/events/common.py` | Q3: `first_stage_for_rule`, `first_stage_of_lot`; Q1 comment |
| `lot_trace/events/purchase_receipt.py` | Q3 route-aware birth + cancel; B3 remaining-availability validation; weaver-duality in `dyed_kg_sold_to_weaver` |
| `lot_trace/public/js/purchase_receipt.js` | **NEW** — B2 + B3 client-side filters & live availability |
| `lot_trace/lot_trace/doctype/lot_consumption_detail/lot_consumption_detail.json` | B3: new `available_kg` read-only field |
| `lot_trace/lot_trace/page/lot_trace_tree/lot_trace_tree.js` | B4 progress + legend |
| `lot_trace/lot_trace/page/lot_trace_tree/lot_trace_tree.css` | B4 per-stage colors + pending style |
| `lot_trace/lot_trace/page/lot_flow/lot_flow.js` | B5 vouchers dialog |
| `lot_trace/lot_trace/page/lot_flow/lot_flow.css` | B5 dialog styles |
| `lot_trace/lot_trace/report/at_weaver_balance/at_weaver_balance.py` | B1 (passes filters through) |
| `lot_trace/lot_trace/report/at_weaver_balance/at_weaver_balance.js` | B1 filter definitions (unchanged behaviour, included for completeness) |

## Deployment

1. Copy every file above into your repo at the same relative path (create `public/js/` if missing).
2. **hooks.py — add one line** (register the new PR client script):
   ```python
   doctype_js = {
       "Purchase Receipt": "public/js/purchase_receipt.js",
       # ...keep any existing entries
   }
   ```
   If `doctype_js` already exists, just add the Purchase Receipt entry.
3. Commit & push, then on the bench:
   ```
   bench --site <site> migrate        # picks up the new available_kg field
   bench build --app lot_trace       # bundles the new JS/CSS
   bench --site <site> clear-cache
   ```
   (On Frappe Cloud: push to the branch and Update/Deploy — migrate + build run automatically.)
4. Hard-refresh the browser (Ctrl+Shift+R) before testing the pages.

## Test Checklist

- [ ] At-Weaver Balance: filter by weaver supplier alone → rows appear; with root lot → still correct.
- [ ] Weaving PR: Root Lot dropdown shows only lots sold to that supplier, with kg labels.
- [ ] Lot Consumption row: pick lot → dyed item auto-fills, Available Kg fills, alert shows; qty > available → red warning; submit still blocks server-side.
- [ ] Second weaving PR against the same lot: availability reflects the earlier consumption.
- [ ] Trace Tree: incomplete lot shows <100% (planned stages basis), pending stages greyed; legend shows 9 distinct colors.
- [ ] Flow Chart: click "+N" → dialog lists all transactions, each opens its doc.
- [ ] Fabric-first: rule with route starting WV → PR births lot at WV, no NT batch.
- [ ] Existing stock: `create_lot_from_stock` → draft Repack SE → submit → lot behaves normally.
