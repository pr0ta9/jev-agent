"""The operation gate. Runs once, before the first round; nothing later can attach or open an operation."""
from __future__ import annotations

import re

from . import questions as Q
from .state import State


def gate(state: State, d) -> None:
    ops = d.vault.ops()
    view = state.view()
    q, th = Q.gate_questions(view, ops, d.settings)
    a = d.pneuma.decide(view, q, th, 0, what="gate")
    if a is None:
        state.ask = {"question": "Is this part of something we were already doing?", "options": [o["id"] for o in ops][:2] + ["something new", "neither"]}
        return
    for o in ops:
        ans = a[f"op__{o['id']}"]
        if ans.choice == "YES" and ans.passed:
            state.operation = o
            break
    else:
        if a["outlives"].choice == "YES" and a["outlives"].passed:
            op_id = re.sub(r"[^a-z0-9]+", "-", state.message.lower()).strip("-")[:40] or "op"
            d.vault.write_op(op_id, state.message)
            state.operation = {"id": op_id, "goal": state.message, "status": "open", "note": ""}
    if d.trace:
        d.trace.write("gate", operation=(state.operation or {}).get("id"), answers={k: v.choice for k, v in a.items()})
