"""Asks pneuma only the round-one triage questions for the four benchmark messages, with the current wording of the
`need` question and with a wording that says general knowledge does not count. Prints the confidences side by side."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from soma import questions as Q  # noqa: E402
from soma.pneuma import Pneuma, choice  # noqa: E402
from soma.settings import load  # noqa: E402
from soma.state import State  # noqa: E402
from soma.tools import CATALOG  # noqa: E402

NEW_NEED = {
    "STATE": "Conversation, opinion, or an answer that is literally present in `kept` or `results`. General knowledge does not count: the writers may only state facts that are in state.",
    "WEB": "Factual content that a web search must fetch first, including things a well-read person would know, because none of it is in state yet.",
    "VAULT": "A file or note from the vault, named or referred to in the message.",
    "WRITE": "A note or file to be written from what is already in state.",
}


def main() -> int:
    s = load(ROOT)
    p = Pneuma(s)
    checks = json.loads((ROOT / "bench/checklists.json").read_text(encoding="utf-8"))
    tools = [{"name": n, "snippet": c["snippet"]} for n, c in CATALOG.items()]
    from soma.trace import recent_turns
    from soma.vault import Vault
    vault = Vault(s.vault)
    vault.index()
    turns = recent_turns(s.traces)
    print(f"{'message':10} {'wording':8} {'context':8} {'need':>14} {'digest':>12} {'prose':>13}")
    for key in ("python313", "fiber", "etias", "rudeus"):
        msg = checks[key]["query"]
        for label, crit in (("current", None), ("new", NEW_NEED)):
          for ctx in ("bare", "bench"):
            state = State(message=msg)
            frags = []
            if ctx == "bench":
                state.turns = turns
                frags = vault.fetch(msg)
                state.fragments = frags
            view = state.view()
            q, th = Q.triage_questions(view, [], tools, None, frags, s)
            if crit:
                q["need"] = choice(q["need"]["instructions"], crit)
            a = p.decide(view, q, th, 1, what="probe")
            if a is None:
                print(key, label, "failed")
                continue
            f = lambda k: f"{a[k].choice} {a[k].confidence:.2f}"
            print(f"{key:10} {label:8} {ctx:8} {f('need'):>14} {f('tool__digest'):>12} {f('prose'):>13}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
