# Testing Lot Trace v2 on Frappe Cloud — Non-Developer Guide

You don't need to code — Frappe Cloud handles the deployment. This guide walks you through uploading, installing, configuring, and testing the app step-by-step.

---

## Part 1: Upload the app to Frappe Cloud

### Option A: Via GitHub (Recommended)

**1. Create a GitHub repo (if you don't have one):**
- Go to [github.com](https://github.com), sign up/login
- Click **New** → create repo named `lot-trace-app`
- Keep it Private (safer) or Public

**2. Upload the app code:**
- Download the `lot_trace` folder from your outputs
- On GitHub, click **Upload files** (in your new repo)
- Drag & drop the entire `lot_trace` folder
- In the commit message, write: `Initial lot_trace v2 app`
- Click **Commit changes**

**3. Connect Frappe Cloud to this repo:**
- Go to [Frappe Cloud dashboard](https://frappecloud.com)
- Click **Apps** (top menu) → **+ New Custom App**
- Fill:
  - **App Name:** `lot_trace`
  - **GitHub Repository URL:** `https://github.com/YOUR-USERNAME/lot-trace-app`
  - **GitHub Branch:** `main`
  - **Public/Private:** match your repo
- Click **Create**

Frappe Cloud will now pull your code. Wait 2–5 minutes.

### Option B: Manual (if GitHub feels complicated)

Ask your Frappe Cloud support chat: _"I have a Python/Frappe app folder. How do I install it on my test site?"_ They can guide you through their CLI or a direct upload. Provide them the `lot_trace` folder.

---

## Part 2: Install on a test site

**1. Create or use a test site:**
- In Frappe Cloud dashboard, click **Sites** → **+ New Site**
- Choose a test site name: `lot-trace-test`
- Set a password
- Click **Create** (wait ~5 min)

OR use an existing test site.

**2. Install the app on the site:**
- Go to your test site → login as Administrator
- Go to **Awesome Bar** (⌘+K or Ctrl+K) → search **App Installer**
- Find `lot_trace` in the list
- Click **Install**
- Wait for the progress bar to finish (1–2 min)

**If it doesn't appear in the list:** In the Awesome Bar, search **Developer** → enable the Developer Mode toggle, then refresh. Try again.

**3. Migrate the database:**
- Go to **Awesome Bar** → **Migrate**
- Click **Migrate**
- Wait for it to finish

All `lot_trace` doctypes (Root Lot, Lot Process Stage, etc.) and custom fields are now in your site.

---

## Part 3: One-time setup (5 minutes)

Before you can trace, configure these masters:

### 3.1 Enable Has Batch No on items

Navigate to: **Home → Stock → Item**

For each of these items, open it and:
- Tick **Has Batch No** checkbox
- **Leave "Automatically Create New Batch" OFF** (the app creates batches automatically)
- Save

**Items to update** (create them if they don't exist):
- `2/10s Cotton Yarn Natural` (the greige yarn)
- `2/10s Cotton Yarn Beige` (dyed yarn)
- `Woven Panel Greige` (weaving pcs)
- `ELSABET THROW BG` (the final product)
- Any intermediate items (Cut Panel, Stitched Panel, etc.) if you want to trace them

### 3.2 Create a Lot Naming Rule

Go to **Awesome Bar** → **Lot Naming Rule** → **+ New**

Fill:
- **Product:** `ELSABET THROW BG`
- **Yarn Item:** `2/10s Cotton Yarn Natural`
- **Prefix:** `EL/TH` (this generates lot codes like `EL/TH/0726/001`)
- **Counter Digits:** `3`
- **Active:** ✓ (checked)
- Click **Save**

Now when you receive greige yarn, the system will auto-generate lot numbers.

### 3.3 Set Lot Trace Settings

Go to **Awesome Bar** → **Lot Trace Settings**

- **Lot Mixing Policy:** `Block` (prevents one Stock Entry from mixing two lots — safest for testing)
- Leave repair doctype names as default
- Click **Save**

### 3.4 Review Lot Process Stages (already set up)

Go to **Awesome Bar** → **Lot Process Stage** → look at the list

You'll see: NT, DY, WV, CT, ST, EM, FN, PK, FG — all pre-loaded with sequence & loss tolerance. You can edit these if your tolerances differ from the defaults (DY: 5%, CT: 2%, ST/EM/FN: 1%).

---

## Part 4: Run the test flow (1 hour)

Now test the end-to-end yarn → IKEA dispatch flow. Use your test site's sample suppliers/customers, or create test ones.

### Create test master data first (15 min):

**Suppliers:**
- Go to **Home → Buying → Supplier** → **+ New**
  - Name: `Ginni Spinners` (yarn supplier)
  - Save
- Create another: `Shree Looms` (weaver — both Customer and Supplier)
- Create: `Rainbow Dyers` (subcontractor)

**Customers:**
- Go to **Home → Selling → Customer** → **+ New**
  - Name: `IKEA` (end customer)
  - Save
- Go back → create `Shree Looms` as a Customer too (same name, different doctype)
  - After saving, on the Customer form, set **Represents Supplier:** `Shree Looms` (link to the Supplier). **This is critical for the weaver bridge.**

**Warehouses** (if not already there):
- Go to **Home → Stock → Warehouse** → verify `Stores - Main` exists (or create it)

### Now run the 8-stage flow:

**Stage 1 — Yarn arrives (Purchase Receipt):**
- Go to **Home → Buying → Purchase Order** → **+ New**
  - Supplier: `Ginni Spinners`
  - Add item row: Item = `2/10s Cotton Yarn Natural`, Qty = `10000`, UOM = `kg`
  - Save & Submit
- Go to **Home → Buying → Purchase Receipt** → **+ New**
  - Against Purchase Order: link to the PO you just made
  - When you link the PO, the items auto-fill
  - **Do NOT manually enter a batch number** — the app creates it
  - Warehouse: `Stores - Main`
  - Click **Submit**
  
✔ **Check:** Open **Home → Stock → Batch** → search for `EL/TH/0726/001-NT`. You should see the greige yarn batch created automatically. Also check **Home → Setup → Lot Trace → Root Lot** and find `EL/TH/0726/001` with Status = `Open`.

**Stage 2 — Send to dyer (Subcontracting):**
- Go to **Home → Stock → Stock Entry** → **+ New**
  - Purpose: `Send to Subcontractor`
  - Subcontractor: `Rainbow Dyers`
  - Add item: Item = `2/10s Cotton Yarn Natural`, Qty = `10000`, Batch = pick `EL/TH/0726/001-NT` (from dropdown)
  - From Warehouse: `Stores - Main`
  - Submit

✔ **Check:** The batch is now "at the subcontractor". Go to **Root Lot** list, find `EL/TH/0726/001`, and note Status is now `In Process`.

**Stage 3 — Dyed yarn received (Subcontracting Receipt):**
- Go to **Home → Manufacturing → Subcontracting Receipt** → **+ New**
  - Subcontractor: `Rainbow Dyers`
  - Set **Lot Stage:** `DY` (from dropdown — tells the system this is the dye output stage)
  - Add item: Item = `2/10s Cotton Yarn Beige`, Qty = `9530` (showing 4.7% dye loss)
  - Click **Submit**

✔ **Check:** Go to **Batch** list, find `EL/TH/0726/001-DY`. If dye loss was > 5%, check **Home → Setup → Lot Trace → Lot Exception** for a Warning. Ignore or mark Resolved.

**Stage 4 — Sell dyed yarn to weaver (DN/SI to weaver):**
- Go to **Home → Selling → Delivery Note** → **+ New**
  - Customer: `Shree Looms` (the weaver-as-Customer)
  - Add item: Item = `2/10s Cotton Yarn Beige`, Qty = `9530`, Batch = pick `EL/TH/0726/001-DY`
  - **Set Dispatch Type = `Intermediate`** (tells the system the lot stays open, not dispatched)
  - Submit

✔ **Check:** Go to **Root Lot**, open `EL/TH/0726/001`, and note the Dyed Yarn is still there (not Completed).

**Stage 5 — ⭐ Weaving pcs received (the BRIDGE — mandatory manual step):**
- Go to **Home → Buying → Purchase Order** → **+ New**
  - Supplier: `Shree Looms` (the weaver-as-Supplier)
  - Add item: Item = `Woven Panel Greige`, Qty = `17800`, UOM = `pcs`
  - **Set Lot Stage = `WV`** (tells the system this is the weaving output stage; also makes Root Lot mandatory on receipt)
  - Save & Submit
- Go to **Home → Buying → Purchase Receipt** → **+ New**
  - Link to the PO you just made
  - In the item row, **before submitting**, fill the **Root Lot field = `EL/TH/0726/001`** (this links the weaved pcs back to the dyed yarn). **This is the linchpin.**
  - Submit

✔ **Check:** Go to **Batch** list, find `EL/TH/0726/001-WV`. The weaving pcs batch now carries the same root lot.

**Stage 6 — Sub-processes (Cutting → Stitching → etc.):**
- Repeat 3× (or more):
  - **Subcontracting Order** (to the relevant subcontractor)
    - Set **Lot Stage** = `CT`, then `ST`, then `FN`, then `PK` (one SCO per stage)
  - **Stock Entry Send to Subcontractor** (pick the input batch, e.g. `-WV` for cutting input)
  - **Subcontracting Receipt** with the output stage and qty

Don't worry about exact quantities — test data just needs to flow through. The system will auto-create the stage batches.

**Stage 7 — Manufacture:**
- Go to **Home → Manufacturing → Work Order** → **+ New**
  - Production Item: `ELSABET THROW BG`
  - Qty to Produce: `17460`
  - **Set Root Lot = `EL/TH/0726/001`**
  - Save & Submit
- Go to **Home → Stock → Stock Entry** → **+ New**
  - Purpose: `Manufacture`
  - Work Order: link to the WO you just made
  - For finished items, Qty = `17460`
  - **Do NOT enter batch** — the system creates `-FG` batch
  - Submit

✔ **Check:** Go to **Batch** list, find `EL/TH/0726/001-FG`. The finished goods batch is created.

**Stage 8 — Final dispatch to IKEA:**
- Go to **Home → Selling → Delivery Note** → **+ New**
  - Customer: `IKEA`
  - Add item: Item = `ELSABET THROW BG`, Qty = `17460`, Batch = pick `EL/TH/0726/001-FG`
  - **Set Dispatch Type = `Final`** (tells the system the lot is now complete)
  - Submit

✔ **Check:** Go to **Root Lot** list, open `EL/TH/0726/001`. Status should now be `Completed`, and Dispatched Qty = `17460`.

---

## Part 5: Verify the trace reports

**Root Lot Trace Report:**
- Go to **Home → Setup → Lot Trace → Lot Trace Reports** (or search **Root Lot Trace**)
- Select **Root Lot:** `EL/TH/0726/001`
- Click **Get Report**
- You'll see every Stock Ledger Entry for all 9 batches in time order, showing the full yarn → IKEA journey

**Order Lot Overview:**
- Search **Order Lot Overview**
- The report shows one row: your lot with yarn received, dyed %, weaved pcs, FG qty, dispatched, and losses per stage

**At-Weaver Balance:**
- Search **At-Weaver Balance**
- Shows `Shree Looms` with 0 balance (all dyed yarn converted to weaving pcs)

---

## Part 6: Test cancellations & edge cases (optional, 30 min)

**Test cancel with downstream:**
- Open the Yarn PR (Stage 1)
- Try to Cancel
- The system should **block** it with a message: "Cannot cancel: lot is already consumed downstream (XX allocations)"
- This is correct — you must cancel documents in reverse order

**Test missing Root Lot on weaving PR:**
- Create a new weaving PO for Shree Looms
- Create a PR against it but **leave Root Lot empty**
- Try to Submit
- The system will **throw an error:** "Root Lot is mandatory"
- This is the guard rail protecting the chain

**Test mixed lots:**
- Create a new yarn receipt (gets lot `EL/TH/0726/002`)
- Create a Stock Entry with both `EL/TH/0726/001-NT` and `EL/TH/0726/002-NT` in the same entry
- Try Submit
- The system will **block** with: "Lot mixing not allowed: Split into one document per lot"
- This is correct

---

## Part 7: If things go wrong

| Problem | Solution |
|---|---|
| Batch not auto-created on PR submit | Check: Item has "Has Batch No" ✓ and "Auto Create Batch" is **OFF** |
| "Root Lot is mandatory" error on weaving PR | The PO row needs the Root Lot field filled before submitting PR |
| "Represents Supplier is not set" error on intermediate DN | Edit the Weaver **Customer** record and set Represents Supplier → Weaver Supplier |
| No Lot Exceptions appearing | They're logged only for loss > tolerance or missing lots. Force one: set Lot Trace Settings → Mixing Policy = Warn, then create an SE with 2 lots. |
| Custom field not showing on forms | Go to **Awesome Bar** → **Customize Form** (per doctype) → scroll down and check the custom field is there and not hidden |

---

## Part 8: Next steps — after testing

Once the flow works end-to-end:

1. **Take screenshots** of key reports (Root Lot Trace, Order Lot Overview) — show your team
2. **Document your learnings** — are the lot codes clear? Is the Dispatch Type field intuitive? Feedback helps refine UX
3. **Test with real data** (sample orders, not your live ERP) — does the loss tolerance match your actual % loss per stage?
4. **Set up print formats** — ask your Frappe admin to add the Lot No column to your final Delivery Note / Sales Invoice so IKEA sees it
5. **Plan rollout** — decide: do you want to trace all new orders from a cutoff date, or backfill existing open orders?

Good luck! If you hit a wall, reply with the error message and I can help debug.
