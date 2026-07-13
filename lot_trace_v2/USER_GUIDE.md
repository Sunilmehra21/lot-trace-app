# Lot Traceability v2 — User Guide
**Batch-based root lot tracking** · ERPNext v14 · app `lot_trace`

---

## 1. The one idea to understand

When greige yarn arrives against a supplier invoice, the system gives it a **Root Lot number** — e.g. **`EL/TH/0726/001`**. That number never changes. As the material moves through dyeing, the weaver, cutting, stitching, and manufacture, the system creates ERPNext **Batches** named with the same lot code plus a stage suffix:

```
EL/TH/0726/001-GY   greige yarn        (Purchase Receipt)
EL/TH/0726/001-DY   dyed yarn          (Subcontracting Receipt)   ~5% loss expected
EL/TH/0726/001-WV   weaved pcs         (Purchase Receipt from weaver)
EL/TH/0726/001-CT   cut pcs            (Subcontracting Receipt)
EL/TH/0726/001-ST   stitched pcs       (Subcontracting Receipt)
EL/TH/0726/001-FG   finished throws    (Manufacture Stock Entry)
```

The final Delivery Note / Sales Invoice to IKEA prints **EL/TH/0726/001** against the dispatched quantity. Second yarn receipt = `EL/TH/0726/002`, tracked in parallel, completely separately.

Because these are normal ERPNext Batches, every stock screen, report, and print format already understands them — you select them the same way you select any batch.

## 2. One-time setup (admin)

1. Tick **Has Batch No** on every traced item: greige yarn, dyed yarn, weaved pcs, each intermediate item, and the finished products. (Leave "Automatically Create New Batch" OFF — the app controls batch creation.)
2. Create the **Lot Naming Rule** per product: ELSABET THROW → `EL/TH/{MMYY}/{###}`, SILOMAL CUSHION → `SI/CC/{MMYY}/{###}`.
3. Review **Lot Process Stages** (GY→DY→WV→CT→ST→EM→FN→PK→FG): sequence, batch suffix, expected loss % (DY = 5%).
4. Give managers the **Lot Manager** role.
5. Attach the **lot-enabled print formats** to Delivery Note and Sales Invoice.

## 3. Daily work, stage by stage

### Stage 1 — Greige yarn arrives (Purchase Receipt)
Just submit the PR. The system automatically creates the Root Lot (`EL/TH/0726/001`) and batch `-GY`, and stamps it on the row. **One PR row = one lot.** If one truck carries yarn for both products, use two rows.
✔ Check: the row shows the new batch; the Root Lot list has a new entry with status Open.

### Stage 2 — Send yarn for dyeing (Subcontracting Order + Stock Entry)
On the Send-to-Subcontractor Stock Entry, pick the `-GY` batch (or let auto-batch FIFO pick). **Rule: one root lot per Stock Entry** — the system warns/blocks if you mix lots. Send lot 001 and lot 002 in separate entries.

### Stage 3 — Dyed yarn comes back (Subcontracting Receipt)
Submit normally. The system reads which `-GY` batch was consumed and auto-creates `-DY` on the received row. If dye loss exceeds the stage tolerance (5%), a **Lot Exception (Warning)** is logged — review it, don't ignore it.

### Stage 4 — Sell dyed yarn to weaver (DN / Sales Invoice)
Set **Dispatch Type = Intermediate**, pick the `-DY` batch. Stock leaves your books, but the lot's "at weaver" balance is tracked — see the **At-Weaver Balance report** anytime.

### Stage 5 — ⭐ Buy weaved pcs back (PO + Purchase Receipt)
The one step needing manual care. On the weaver's PO/PR row, the **Root Lot field is mandatory** — select which lot's dyed yarn these pcs were woven from. The system then auto-creates batch `-WV` under that lot. Without the root lot, the PR will not submit — this is the bridge that keeps the chain unbroken.

### Stage 6 — Sub-processes (cutting, stitching, embroidery, finishing, packing)
Each is a Subcontracting Order (with its **Process Stage** set: CT, ST, EM...) + send Stock Entry + SCR. Batches inherit automatically exactly like the dye stage. Nothing manual except picking the input batch.

### Stage 7 — Final manufacture (Work Order + Stock Entry Manufacture)
Set **Root Lot** on the Work Order (one WO per lot recommended). Inputs are validated against the lot; the finished-goods batch `-FG` is created automatically.

### Stage 8 — Final dispatch to IKEA (DN / Sales Invoice)
Set **Dispatch Type = Final**, pick `-FG` batch(es). If dispatching from two lots, use two rows — each row prints its own lot number. The printout shows the Root Lot per line, as IKEA requires. The Root Lot flips to **Completed** when its FG qty is fully dispatched.

### Repairs (any stage)
On Repair Issue / Repair Receipt, select the batch being repaired — the root lot follows automatically and the repair appears in the lot's trace history.

## 4. Answering the two golden questions

- **"Show me everything about lot EL/TH/0726/001"** → open **Root Lot Trace** report (or the Lot Flow page for the visual): every movement of every stage batch, from the supplier invoice to the IKEA dispatch, in order, with running quantities and loss at each stage.
- **"This throw in dispatch DN-0092 — where did its yarn come from?"** → the DN row shows batch `EL/TH/0726/001-FG` → that IS the answer; open the Root Lot for the full backward story including the yarn supplier's invoice.

## 5. Rules your team must follow (print this)

1. **One PR row per yarn invoice lot.** New invoice/lot = new row (or new PR).
2. **Never mix root lots in one Stock Entry / SCR / WO.** Separate documents per lot. The system enforces this; the override is for managers only and gets logged.
3. **Weaved-pcs PR: always fill Root Lot.** The system blocks you if you forget.
4. **Set Dispatch Type on every DN/SI** — Intermediate (to weaver) or Final (to IKEA).
5. **Review Lot Exceptions daily** (Lot Manager): loss out of tolerance, missing root lot, mixed-lot overrides, weaver balance mismatch. Target zero unresolved.
6. Cancel documents in reverse order (newest first) — same as standard ERPNext batch behavior.

## 6. FAQ

**Why does the batch have "-DY" at the end? IKEA wants the plain lot number.**
Batch IDs must be unique per item in ERPNext, so each stage's item gets a suffixed batch. All prints and reports show the **Root Lot** (without suffix) — the suffix is internal plumbing.

**The weaver mixed two of our lots on his loom. What now?**
Ask the weaver to declare the split (e.g. 60% lot 001, 40% lot 002) and make two PR rows, one per root lot with the split qty. If truly inseparable, a manager uses the mixed-lot override on one row — logged as an exception with both lots recorded.

**Yarn from lot 002 was used for the other product.**
Use the Root Lot re-assignment action (Lot Manager) — it re-links the lot to the other product with an audit trail.

**We received 10,000 kg but the lot shows less at a later stage.**
Normal — process loss. The Order Lot Overview shows loss % per stage; exceptions fire when a stage exceeds its tolerance.

**Do batches slow down our 2-lakh-pc order?**
No. One order ≈ 10–30 root lots ≈ under ~300 batch records total. ERPNext handles thousands of batches routinely.
