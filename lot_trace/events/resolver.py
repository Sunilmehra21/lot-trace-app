# -*- coding: utf-8 -*-
# Phase 6 — Core Resolver
# Single source of truth for: which profile, which lot, what batch name.
#
# Design rules implemented here (locked July 2026):
#   1. ONE Root Lot per production lot (not per yarn item).
#   2. The PRIMARY yarn is the ONLY trigger that can OPEN a new lot
#      (and increment the serial 01 -> 02 -> 03).
#   3. A SECONDARY yarn NEVER creates or increments a lot. It attaches to an
#      already-open lot that is still "waiting" for that yarn item.
#   4. When several open lots are waiting for the same secondary yarn and there
#      is no PO link, pick the OLDEST open lot (FIFO). Ask the user only if two
#      lots were opened on the same day (genuine tie).
#
# This module ONLY decides names and links. It never touches stock/SLE/valuation.

import re
import frappe
from frappe.utils import nowdate


# ---------------------------------------------------------------------------
# Profile resolution
# ---------------------------------------------------------------------------

def resolve_profile_for_item(item_code):
    """Return (profile_name, trace_row) for a greige yarn item, or (None, None).

    A greige yarn item appears in exactly one active Lot Trace Profile's
    Trace Items table. We match on the greige item directly.
    """
    if not item_code:
        return None, None

    rows = frappe.get_all(
        "Lot Trace Item",
        filters={"yarn_item": item_code},
        fields=["parent", "name", "role", "item_abbr", "yarn_item", "bom_kg_per_pc"],
    )
    for r in rows:
        active = frappe.db.get_value("Lot Trace Profile", r.parent, "active")
        if active:
            return r.parent, r
    return None, None


def resolve_profile_for_dyed_item(dyed_item_code):
    """Map a dyed item back to its (profile, trace_row) via the base greige item.

    Used as a FALLBACK only. The primary path in subcontracting resolves the
    lot from the consumed greige batch, which is far more reliable.
    """
    base = extract_base_yarn_item(dyed_item_code)
    if not base:
        return None, None
    return resolve_profile_for_item(base)


def get_profile_doc(profile_name):
    return frappe.get_doc("Lot Trace Profile", profile_name)


def get_primary_row(profile_name):
    """Return the single primary Trace Item row of a profile."""
    rows = frappe.get_all(
        "Lot Trace Item",
        filters={"parent": profile_name, "role": "Primary"},
        fields=["name", "item_abbr", "yarn_item", "bom_kg_per_pc"],
    )
    if not rows:
        return None
    return rows[0]


# ---------------------------------------------------------------------------
# Lot serial / code generation
# ---------------------------------------------------------------------------

def _render_lot_code(pattern, serial):
    """Fill a lot code pattern. Tokens: {MMYY}, {##} (zero-padded serial).

    Width of the serial is taken from the number of '#' characters, min 2.
    """
    mmyy = nowdate_mmyy()
    out = pattern.replace("{MMYY}", mmyy)

    m = re.search(r"\{(#+)\}", out)
    if m:
        width = max(2, len(m.group(1)))
        out = out[: m.start()] + str(serial).zfill(width) + out[m.end():]
    else:
        # No serial token in pattern -> append it to stay unique.
        out = f"{out}/{str(serial).zfill(2)}"
    return out


def nowdate_mmyy():
    d = nowdate()  # 'YYYY-MM-DD'
    yyyy, mm, _dd = d.split("-")
    return f"{mm}{yyyy[2:]}"


def next_lot_serial(profile_name):
    """Next serial for this profile within the current MMYY period.

    Serial is scoped per profile per month, matching the {MMYY}/{##} pattern.
    Reads existing Root Lots of this profile in this period and adds 1.
    """
    mmyy = nowdate_mmyy()
    existing = frappe.get_all(
        "Root Lot",
        filters={"profile": profile_name, "period_mmyy": mmyy},
        fields=["serial"],
        order_by="serial desc",
        limit=1,
    )
    if existing and existing[0].serial:
        return int(existing[0].serial) + 1
    return 1


# ---------------------------------------------------------------------------
# THE core decision: which lot does an incoming greige receipt belong to?
# ---------------------------------------------------------------------------

def resolve_open_lot(item_code, po_root_lot=None, on_ambiguous="fifo"):
    """Decide the Root Lot for an incoming greige yarn receipt row.

    Returns a dict:
        {"action": "reuse"|"create", "root_lot": <name-or-None>,
         "profile": <name>, "trace_row": <dict>, "role": "Primary"|"Secondary",
         "ambiguous": bool, "candidates": [names]}

    Rules:
      PRIMARY yarn:
        - Always CREATE a new lot (new production run, serial +1).
          (Primary is the trigger; a second primary receipt = a new run.)
      SECONDARY yarn:
        - Must attach to an OPEN lot still WAITING for this item.
        - If po_root_lot given and it is open+waiting -> reuse it.
        - Else pick among open+waiting lots:
            * exactly one       -> reuse it
            * none              -> HOLD (needs primary first) -> action 'create'
                                   is NOT allowed for secondary; caller decides
            * many, FIFO tie ok -> oldest (by creation) unless same-day tie
    """
    profile, trace_row = resolve_profile_for_item(item_code)
    if not profile:
        return {"action": None, "root_lot": None, "profile": None,
                "trace_row": None, "role": None, "ambiguous": False,
                "candidates": []}

    role = trace_row.role

    if role == "Primary":
        return {"action": "create", "root_lot": None, "profile": profile,
                "trace_row": trace_row, "role": role, "ambiguous": False,
                "candidates": []}

    # --- Secondary yarn: never creates a lot, only attaches ---
    # An explicit PO link wins if that lot is still waiting for this item.
    if po_root_lot and _lot_is_waiting_for(po_root_lot, item_code):
        return {"action": "reuse", "root_lot": po_root_lot, "profile": profile,
                "trace_row": trace_row, "role": role, "ambiguous": False,
                "candidates": [po_root_lot]}

    candidates = _open_lots_waiting_for(profile, item_code)

    if len(candidates) == 1:
        return {"action": "reuse", "root_lot": candidates[0], "profile": profile,
                "trace_row": trace_row, "role": role, "ambiguous": False,
                "candidates": candidates}

    if len(candidates) == 0:
        # No open lot is waiting for this secondary yarn. It arrived before its
        # primary. Caller (PR handler) will surface a clear message.
        return {"action": "hold", "root_lot": None, "profile": profile,
                "trace_row": trace_row, "role": role, "ambiguous": False,
                "candidates": []}

    # Multiple open lots waiting. Default FIFO = oldest creation.
    ordered = _order_lots_fifo(candidates)
    oldest = ordered[0]
    same_day_tie = _same_day_tie(ordered)

    return {"action": "reuse", "root_lot": oldest, "profile": profile,
            "trace_row": trace_row, "role": role,
            "ambiguous": bool(same_day_tie and on_ambiguous != "fifo"),
            "candidates": ordered}


def _lot_is_waiting_for(root_lot, item_code):
    """True if root_lot is open (intake not complete) and has no NT batch yet
    for this specific greige item."""
    rl = frappe.db.get_value(
        "Root Lot", root_lot, ["intake_complete", "profile"], as_dict=True
    )
    if not rl or rl.intake_complete:
        return False
    # Already has a receipt for this item?
    has = frappe.db.exists(
        "Lot Receipt", {"parent": root_lot, "yarn_item": item_code}
    )
    return not has


def _open_lots_waiting_for(profile, item_code):
    """All open lots of this profile with no NT receipt yet for item_code."""
    open_lots = frappe.get_all(
        "Root Lot",
        filters={"profile": profile, "intake_complete": 0},
        fields=["name"],
        order_by="creation asc",
    )
    waiting = []
    for lot in open_lots:
        has = frappe.db.exists(
            "Lot Receipt", {"parent": lot.name, "yarn_item": item_code}
        )
        if not has:
            waiting.append(lot.name)
    return waiting


def _order_lots_fifo(lot_names):
    rows = frappe.get_all(
        "Root Lot",
        filters={"name": ["in", lot_names]},
        fields=["name", "creation"],
        order_by="creation asc",
    )
    return [r.name for r in rows]


def _same_day_tie(ordered_lot_names):
    """True if the two oldest waiting lots were created on the same calendar
    day (a genuine tie where FIFO is ambiguous)."""
    if len(ordered_lot_names) < 2:
        return False
    rows = frappe.get_all(
        "Root Lot",
        filters={"name": ["in", ordered_lot_names[:2]]},
        fields=["name", "creation"],
    )
    days = {str(r.creation)[:10] for r in rows}
    return len(days) == 1


# ---------------------------------------------------------------------------
# Batch naming (pattern-driven, from the profile's Batch Naming Rules)
# ---------------------------------------------------------------------------

def render_batch_name(profile_name, root_lot_code, stage_code, trace_row=None,
                      color_abbr=None):
    """Build a batch name from the profile's Batch Naming Rules for a stage.

    Tokens:
      {LOT}   -> root lot code
      {ABBR}  -> trace item's user-defined abbr (A, B, ...)
      {COLOR} -> colour abbr (for dyed stages); token dropped if empty
      {STAGE} -> stage code
    Adjacent duplicate '-' left by an empty token are collapsed.
    """
    pattern = _batch_pattern_for_stage(profile_name, stage_code)
    abbr = (trace_row or {}).get("item_abbr") if isinstance(trace_row, dict) \
        else getattr(trace_row, "item_abbr", None)

    out = pattern.replace("{LOT}", root_lot_code or "")
    out = out.replace("{ABBR}", abbr or "")
    out = out.replace("{COLOR}", color_abbr or "")
    out = out.replace("{STAGE}", stage_code or "")

    # Collapse artefacts from empty tokens: '--' -> '-', trim stray dashes.
    out = re.sub(r"-{2,}", "-", out).strip("-")
    return out


def _batch_pattern_for_stage(profile_name, stage_code):
    pattern = frappe.db.get_value(
        "Lot Batch Naming Rule",
        {"parent": profile_name, "stage": stage_code},
        "pattern",
    )
    if pattern:
        return pattern
    # Sensible defaults if the profile has no explicit rule for this stage.
    return {
        "NT": "{LOT}-{ABBR}-NT",
        "DY": "{LOT}-{ABBR}-{COLOR}-DY",
        "WV": "{LOT}-WV",
        "CT": "{LOT}-CT",
    }.get(stage_code, "{LOT}-{STAGE}")


# ---------------------------------------------------------------------------
# Item helpers (shared)
# ---------------------------------------------------------------------------

def extract_base_yarn_item(item_code):
    """Strip dye/cut/colour suffixes to recover the greige item code.

    RM-YN-COTTON-CN-DYE-BK -> RM-YN-COTTON-CN
    RM-YN-CHENILLE-CN-DY   -> RM-YN-CHENILLE-CN
    """
    if not item_code:
        return None
    m = re.match(
        r"(.*?-(?:CN|RM|WL|SLK|YRN|POL)?)(?:-DYE|-DY|-CT)?(?:-[A-Z]{2,})?$",
        item_code,
    )
    if m:
        return m.group(1).rstrip("-")
    return item_code


def color_abbr_for_item(item_code):
    """Best-effort colour abbreviation for a dyed item.

    1) Item Variant Attribute 'Colour' abbr, 2) trailing code segment,
    3) first 2-4 chars fallback.
    """
    if not item_code:
        return None

    # 1) Variant attribute
    try:
        attr = frappe.db.get_value(
            "Item Variant Attribute",
            {"parent": item_code, "attribute": ["like", "%Colour%"]},
            "attribute_value",
        ) or frappe.db.get_value(
            "Item Variant Attribute",
            {"parent": item_code, "attribute": ["like", "%Color%"]},
            "attribute_value",
        )
        if attr:
            abbr = frappe.db.get_value(
                "Item Attribute Value",
                {"attribute_value": attr},
                "abbr",
            )
            if abbr:
                return abbr.upper()
    except Exception:
        pass

    # 2) Trailing segment after -DYE-/-DY-
    m = re.search(r"-(?:DYE|DY)-([A-Z0-9]{2,})$", item_code.upper())
    if m:
        return m.group(1)

    # 3) Fallback
    return re.sub(r"[^A-Z0-9]", "", item_code.upper())[:3] or None
