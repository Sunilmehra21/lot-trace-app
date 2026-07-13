# Lot Traceability v2 — Design & Implementation Plan
**Approach: Native ERPNext Batch + thin custom app `lot_trace`** · Target: ERPNext v14

---

## 1. The requirement (from "Traceability Flow" document)

- IKEA order: 2 products (ELSABET THROW 80,000 nos; SILOMAL CUSHION COVER 120,000 nos), needing 81,480 kg greige yarn (incl. 5% dye loss).
- Yarn arrives against **multiple supplier invoices over time**. Each receipt = **one new Root Lot**, numbered like **`EL/TH/0726/001`**, `EL/TH/0726/002`, ...
- **The same lot number must carry through every stage** — greige yarn → dye (subcontract) → dyed yarn sold to weaver → weaved pcs purchased back → sub-processes (cutting, stitching, embroidery, finishing, packing — subcontracted) → final manufacture → **final dispatch, where the lot number is mentioned on the Sales Invoice / Delivery Note** to the end customer.
- Multiple lots run **in parallel and are traced separately**. Forward and backward trace by lot number.
- Repairs at any stage via custom Repair Issue / Repair Receipt doctypes.

## 2. Decision: Batch vs Serial vs Custom module

| Option | Verdict | Why |
|---|---|---|
| **Serial No** | ❌ Rejected | 200,000 serials per order; unusable data entry and performance. |
| **Native Batch only** | ❌ Not enough | (a) A batch ID is globally unique and belongs to ONE item — the same `EL/TH/0726/001` cannot exist for yarn *and* dyed yarn *and* the finished throw. (b) The dyed-yarn-sale → weaved-pcs-purchase loop breaks the chain (stock exits the books). (c) Output batches don't inherit identity from input batches. (d) No lot-level trace reports. |
| **Fully custom lot module** (v1 design) | ⚠️ Works but heavy | Duplicates stock tracking that Batch already does; more code to maintain; lot number doesn't appear natively on stock docs/prints. |
| **✅ HYBRID: Batch carrier + `lot_trace` app** | **RECOMMENDED** | Batch flows natively through PR, Stock Entry, SCR, DN/SI and the Stock Ledger; invoice printing of batch is built-in. The custom app only adds: Root Lot registry, stage-batch auto-creation/inheritance, the weaver bridge, guard rails, and reports/tree. ~40% of the custom-module code, upgrade-safe, core untouched. |

### The naming trick that makes Batch work
One Root Lot = a family of stage batches sharing the root code as prefix:

| Stage | Item | Batch ID |
|---|---|---|
| Greige yarn receipt | 2/10s Cotton Yarn Natural | `EL/TH/0726/001-GY` |
| Dyed yarn (SCR) | 2/10s Cotton Yarn Beige | `EL/TH/0726/001-DY` |
| Weaved pcs (PR from weaver) | Woven Panel Greige | `EL/TH/0726/001-WV` |
| Sub-process outputs (SCR) | Cut/Stitched/Embroidered pcs | `EL/TH/0726/001-CT`, `-ST`, `-EM`, `-FN`, `-PK` |
| Finished goods (Manufacture) | ELSABET THROW BG | `EL/TH/0726/001-FG` |

Every batch carries custom fields `root_lot` + `process_stage`. The **final SI/DN prints the root lot** (`EL/TH/0726/001`) from the batch — exactly as required. Forward/backward trace = all Stock Ledger Entries of all batches under one root lot, in time order.

## 3. Data model (custom app `lot_trace`)

### 3.1 DocType: Root Lot
The registry — one record per yarn receipt lot.
- `lot_code` (name), e.g. `EL/TH/0726/001` — generated from Lot Naming Rule
- `sales_order` (Link) — the IKEA order; `product` (Link Item) — final product this lot is destined for
- `customer`, `yarn_item`, `supplier`, `supplier_invoice` (PR reference)
- `received_qty` (kg), `uom`
- `current_stage` (Link Process Stage) — auto-updated as stage batches are created
- `status`: Open / In Process / Completed (FG dispatched) / Short Closed
- `remarks`

### 3.2 DocType: Lot Process Stage (master, fixture)
- `stage_code` (GY, DY, WV, CT, ST, EM, FN, PK, FG), `stage_name`, `sequence`, `batch_suffix`, `expected_loss_pct` (e.g. DY = 5%), `is_external_custody` (for dyed yarn at weaver), `erp_doc_hint`

### 3.3 DocType: Lot Naming Rule
Per Sales Order item (or default): `prefix_1` (product short code, EL/SI), `prefix_2` (TH/CC), `period_format` (MMYY from receipt date), `counter_digits`. Produces `EL/TH/0726/###`.

### 3.4 Custom Fields (fixtures)
| DocType | Field |
|---|---|
| **Batch** | `root_lot` (Link Root Lot), `process_stage` (Link Lot Process Stage) |
| Purchase Order (yarn + weaved pcs) | `sales_order_ref`, `for_product` (Link Item) |
| Purchase Order Item / PR Item (weaved pcs) | **`root_lot` (Link, mandatory for weaver POs)** |
| Subcontracting Order | `process_stage` |
| Delivery Note / Sales Invoice | `dispatch_type` (Intermediate / Final) |
| Work Order | `root_lot` (recommended: one WO per lot) |
| Repair Issue / Repair Receipt (custom doctypes) | `root_lot`, `batch_no`, `process_stage` |

### 3.5 DocType: Lot Exception
Same as v1: Missing Root Lot, Mixed Lots Warning, Loss Out of Tolerance, Weaver Balance Mismatch — with severity, resolved flag.

*(No custom stock ledger needed — `tabStock Ledger Entry.batch_no` already records every movement of every stage batch.)*

## 4. Flow-by-flow behavior (hooks)

1. **Greige Yarn PR** (`on_submit`): for each item row → create **Root Lot** (next number from naming rule) + **Batch `{lot}-GY`** → set batch on the PR row. One PR row = one lot. *(Batch creation happens in `before_validate` so the row saves with the batch.)*
2. **Send to Subcontractor (dye)**: native batch selection — user (or auto-FIFO) picks `-GY` batches. **Guard rail:** warn if one Stock Entry mixes root lots (configurable: block/warn).
3. **Subcontracting Receipt (dyed yarn)**: hook reads consumed supplied-item batches → determines root lot → auto-creates **Batch `{lot}-DY`** on the received row. Computes dye loss vs `expected_loss_pct` → Lot Exception if out of tolerance.
4. **Dyed yarn DN/SI to weaver** (`dispatch_type = Intermediate`): native batch on rows (`-DY`). App records "external custody" for the lot: qty at weaver = sold − weaved-pcs-received-equivalent (report, not ledger).
5. **Weaved pcs PO/PR from weaver**: **`root_lot` mandatory on the row** (this is the bridge across the sale/buy-back gap). Hook auto-creates **Batch `{lot}-WV`** on the PR row. Validation: root lot must have `-DY` qty sold to this weaver.
6. **Sub-process SCO/SCR loops** (cutting → stitching → embroidery → finishing → packing): same as step 3 — consumed batch's root lot → output batch `{lot}-{next suffix}`. Stage sequence comes from Lot Process Stage master; the SCO's `process_stage` field picks the suffix.
7. **Manufacture (Work Order + Stock Entry)**: WO carries `root_lot`; input batches validated against it; FG batch **`{lot}-FG`** auto-created on the manufacture entry. FG item has "Has Batch No" ✓, so 80,000 throws = a handful of `-FG` batches (one per root lot), not 80,000 records.
8. **Final DN/SI** (`dispatch_type = Final`): user/auto picks `-FG` batches. **Print format shows Root Lot** (fetched from batch). Root Lot status → Completed when dispatched qty reaches lot's FG qty.
9. **Repair Issue/Receipt** (custom doctypes): rows carry `batch_no` + `root_lot`; movements appear in the lot trace via their stock entries.
10. **Cancels**: native batch/SLE reversal is automatic. App hooks only clean up auto-created batches if unused, and reopen Root Lot status.

**Lot mixing policy** (the one hard business rule to confirm): default = **one root lot per transaction** (block mixing) with a "Allow mixed lots" override that logs a Warning exception and splits by batch qty. Real production sometimes must blend lots — the override keeps the system honest instead of forcing workarounds.

## 5. Reports & UI

1. **Root Lot Trace** (the star report): filter by root lot → every SLE of every stage batch in time order: date, stage, document, warehouse/party, in-qty, out-qty, running balance. This IS the forward+backward trace.
2. **Order Lot Overview**: per Sales Order → one row per root lot: received kg → dyed kg (loss %) → at-weaver kg → weaved pcs → per sub-stage qty → FG qty → dispatched qty → status.
3. **Lot Flow Chart page** (`/app/lot-flow`): visual swimlane — one band per root lot flowing across stage columns (the chart view mockup shows this).
4. **At-Weaver Balance report**: dyed yarn sold minus consumed by weaved-pcs receipts, per weaver per lot.
5. **Lot Exception list** — daily review.
6. **Print formats**: final SI/DN with a Lot column (root lot per row); optional lot annexure listing stage history for customer compliance (IKEA audit).

## 6. Implementation phases (single Frappe dev)

| Phase | Scope | Time |
|---|---|---|
| 1 | App skeleton; Root Lot, Lot Process Stage, Lot Naming Rule, Lot Exception doctypes; Batch custom fields; enable Has Batch No on traced items | 1 wk |
| 2 | Greige PR hook (lot birth) + dye loop (send/SCR inheritance) + guard rails | 1.5 wk |
| 3 | Weaver bridge (DN/SI intermediate + weaved-pcs PR with mandatory root lot) | 1 wk |
| 4 | Sub-process SCR chain + Manufacture + final dispatch + print formats | 1.5 wk |
| 5 | Reports (Root Lot Trace, Order Lot Overview, At-Weaver Balance) + Lot Flow page | 1.5 wk |
| 6 | Repair doctypes integration; cancel/amend handling; exceptions polish | 1 wk |
| 7 | UAT on staging with one real lot end-to-end; pilot on one live order | 2 wk |
| | **Total** | **~9–10 weeks** |

## 7. What carries over from the v1 build

From the earlier `garment_traceability` app: the **Exception doctype pattern, report SQL structure, trace tree/flow UI, fixtures/hooks scaffolding, and the guard-rail philosophy** (manual selection where guessing is dangerous) all carry over. What's replaced: the custom Trace Lot/Movement/Allocation ledger — native Batch + Stock Ledger Entry now plays that role. The v1 codebase remains a valid fallback if you later need many-to-many lot blending genealogy, which the batch approach handles only via the mixed-lot override.

## 8. Open points to confirm before build

1. **Lot mixing:** is one-lot-per-transaction acceptable as the default rule? (Recommended: yes, with logged override.)
2. **Lot ↔ product binding:** lot `EL/TH/...` is for ELSABET — confirmed that a lot's yarn is never diverted to the other product? (If diversion happens, we add a re-assignment feature with audit log.)
3. Confirm the **stage list & suffixes** (GY, DY, WV, CT, ST, EM, FN, PK, FG) and expected loss % per stage.
4. Weaved-pcs UOM conversion (kg yarn → pcs/mtr panels) — needed for the At-Weaver Balance report.
5. Are Repair Issue/Receipt doctypes already built, or part of this scope?
