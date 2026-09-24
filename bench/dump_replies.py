"""Writes every baseline reply with its question's fact list and the regex hits, for reading by hand."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
d = json.loads((ROOT / "bench/baselines.json").read_text(encoding="utf-8"))
checks = json.loads((ROOT / "bench/checklists.json").read_text(encoding="utf-8"))
out = []
for key in ("python313", "fiber", "etias", "rudeus"):
    facts = list(checks[key]["facts"].items())
    out.append("########## " + key + " FACTS: " + " | ".join(f"[{i}] {n}" for i, (n, _) in enumerate(facts)))
    for agent in d:
        r = d[agent].get(key)
        if not r:
            continue
        hits = [i for i, (n, g) in enumerate(facts) if all(any(re.search(a, r["text"], re.I) for a in gg) for gg in g)]
        out.append(f"===== {agent} ({key}) regex hits {hits} of {len(facts)}")
        out.append(r["text"][:3500])
        out.append("")
(ROOT / "bench/replies-for-reading.txt").write_text("\n".join(out), encoding="utf-8")
print("chars", sum(len(x) for x in out))
