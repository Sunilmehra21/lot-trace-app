# Lot Trace

Root-Lot traceability for ERPNext v14 using **native Batch** as the carrier.
One lot number (`EL/TH/0726/001`) is born at greige yarn Purchase Receipt and rides
through every stage as stage-suffixed batches (`-NT`, `-DY`, `-WV`, `-CT`, `-ST`,
`-EM`, `-FN`, `-PK`, `-FG`) linked by a `root_lot` field, until it prints on the
final Sales Invoice / Delivery Note.

## Install

```bash
cd frappe-bench
# copy this folder to apps/lot_trace (or bench get-app from your git)
bench --site yoursite install-app lot_trace
bench --site yoursite migrate
```

## Setup after install

1. **Items:** tick *Has Batch No* on greige yarn, dyed yarn, weaved pcs, all
   intermediate items, and finished products. Leave *Automatically Create New Batch* OFF.
2. **Lot Naming Rule:** one per final product, e.g. product = ELSABET THROW BG,
   yarn item = 2/10s Cotton Yarn Natural, prefix = `EL/TH` → lots `EL/TH/0726/001`.
3. **Lot Trace Settings:** mixing policy (Block recommended), repair doctype names
   (defaults: Repair Issue / Repair Receipt).
4. **Weaving POs:** set *Lot Stage = WV*; the Root Lot field on their PR rows is mandatory.
5. **Subcontracting Orders:** set *Lot Stage* (DY, CT, ST, EM, FN, PK).
6. **BOM for weaved pcs item** must contain the dyed yarn item — the At-Weaver
   Balance report reads kg-per-pc from it.
7. Roles: give **Lot Manager** to supervisors, **Lot User** to entry staff.
8. **Print format:** add to your SI/DN format, in the items table:
   `{{ frappe.db.get_value("Batch", row.batch_no, "root_lot") or "" }}` as a "Lot No" column.

## What is automated vs manual

| Event | Automation |
|---|---|
| Yarn PR | Root Lot + `-NT` batch created & assigned automatically |
| Subcontracting Receipt | Output batch (`-DY`/`-CT`/...) auto-created from consumed batch's lot; loss checked vs stage tolerance |
| Manufacture Stock Entry | `-FG` batch auto-created; inputs validated against WO's Root Lot |
| Weaved-pcs PR | **Manual:** Root Lot on row is mandatory (the sale/buy-back bridge) |
| Any multi-row stock doc | One root lot per document enforced (Block/Warn per settings) |
| Final DN/SI | Dispatched qty tracked; Root Lot auto-completes |

## Utilities (bench console)

```python
from lot_trace.api.lot import get_lot_trace, reassign_lot, at_weaver_balance
get_lot_trace("EL/TH/0726/001")        # full movement history
reassign_lot("EL/TH/0726/002", "SILOMAL CUSHION COVER 40X40 BG", "yarn diverted")  # audited
at_weaver_balance("Shree Looms")       # dyed yarn lying at weaver, per lot
```

Reports: **Root Lot Trace**, **Order Lot Overview**, **At-Weaver Balance**.
Exceptions: review the **Lot Exception** list daily (Lot Manager).
