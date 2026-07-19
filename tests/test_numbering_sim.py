# -*- coding: utf-8 -*-
# Phase 6 — Numbering-rule simulation test.
#
# This proves the locked lot-counter behaviour WITHOUT a live Frappe DB, by
# re-implementing ONLY the decision logic of resolver.resolve_open_lot against
# an in-memory store. If this passes, the numbering design is correct:
#
#   * PRIMARY yarn always opens a new lot (serial +1).
#   * SECONDARY yarn reuses the oldest open lot waiting for it (FIFO).
#   * SECONDARY yarn with no open lot -> HOLD (must receive primary first).
#
# Run:  python test_numbering_sim.py     (plain python, no frappe needed)

from itertools import count


class FakeStore:
    """Minimal in-memory mirror of Root Lot + Lot Receipt for the sim."""

    def __init__(self):
        self.lots = {}          # name -> {profile, serial, intake_complete, seq}
        self.receipts = set()   # (lot, yarn_item)
        self._seq = count(1)
        self._serial_by_period = {}

    def create_lot(self, profile):
        period = "0726"
        s = self._serial_by_period.get((profile, period), 0) + 1
        self._serial_by_period[(profile, period)] = s
        name = f"MV/BG/{period}/{s:02d}"
        self.lots[name] = {
            "profile": profile, "serial": s, "intake_complete": False,
            "seq": next(self._seq),
        }
        return name

    def add_receipt(self, lot, yarn_item, profile_items):
        self.receipts.add((lot, yarn_item))
        got = {i for (l, i) in self.receipts if l == lot}
        if set(profile_items).issubset(got):
            self.lots[lot]["intake_complete"] = True

    def open_lots_waiting_for(self, profile, yarn_item):
        out = [
            (name, d["seq"]) for name, d in self.lots.items()
            if d["profile"] == profile and not d["intake_complete"]
            and (name, yarn_item) not in self.receipts
        ]
        out.sort(key=lambda t: t[1])  # FIFO by creation seq
        return [name for name, _ in out]


PROFILE = "ELSABET THROW"
PROFILE_ITEMS = ["COTTON", "CHENILLE"]
ROLE = {"COTTON": "Primary", "CHENILLE": "Secondary"}


def decide(store, yarn_item):
    """Mirror of resolver.resolve_open_lot's action for the sim."""
    role = ROLE[yarn_item]
    if role == "Primary":
        return "create", None
    waiting = store.open_lots_waiting_for(PROFILE, yarn_item)
    if len(waiting) == 1:
        return "reuse", waiting[0]
    if not waiting:
        return "hold", None
    return "reuse", waiting[0]  # FIFO oldest


def receive(store, yarn_item):
    action, lot = decide(store, yarn_item)
    if action == "create":
        lot = store.create_lot(PROFILE)
    if action == "hold":
        return "HOLD", None
    store.add_receipt(lot, yarn_item, PROFILE_ITEMS)
    return action.upper(), lot


def run():
    s = FakeStore()
    results = []

    # Jul 1: Cotton (primary) -> new lot 01
    results.append(("Cotton", *receive(s, "COTTON")))
    # Jul 3: Chenille (secondary) -> reuse 01
    results.append(("Chenille", *receive(s, "CHENILLE")))
    # Jul 15: Cotton again (primary, new run) -> new lot 02
    results.append(("Cotton", *receive(s, "COTTON")))
    # Jul 17: Chenille -> reuse 02 (01 already complete)
    results.append(("Chenille", *receive(s, "CHENILLE")))
    # Aug 2: Cotton -> new lot 03
    results.append(("Cotton", *receive(s, "COTTON")))

    for yarn, action, lot in results:
        print(f"  {yarn:10s} -> {action:6s} {lot}")

    lots = [r[2] for r in results]
    assert lots[0] == "MV/BG/0726/01", lots
    assert lots[1] == "MV/BG/0726/01", "Chenille must REUSE lot 01"
    assert lots[2] == "MV/BG/0726/02", "2nd cotton must CREATE lot 02"
    assert lots[3] == "MV/BG/0726/02", "2nd chenille must REUSE lot 02"
    assert lots[4] == "MV/BG/0726/03", "3rd cotton must CREATE lot 03"
    assert results[0][1] == "CREATE"
    assert results[1][1] == "REUSE"
    assert results[2][1] == "CREATE"
    assert results[4][1] == "CREATE"

    # Secondary-before-primary -> HOLD
    s2 = FakeStore()
    action, lot = receive(s2, "CHENILLE")
    assert action == "HOLD", "Secondary with no open lot must HOLD"
    print("  Chenille-first -> HOLD (correct: needs primary)")

    print("\nALL NUMBERING ASSERTIONS PASSED ✓")
    print("Primary triggers 01,02,03; secondary reuses; FIFO honoured.")


if __name__ == "__main__":
    run()
