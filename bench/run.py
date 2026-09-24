"""Runs the acceptance set and prints a table. Live: needs .env, SearXNG and Codex."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SOMA_ROOT", str(ROOT))

from soma import loop  # noqa: E402
from soma.learn import accept  # noqa: E402
from soma.settings import load  # noqa: E402
from soma.trace import read  # noqa: E402

LIMITS = {"python313": 120, "fiber": 41, "etias": 39, "rudeus": 128}
FLOORS = {"python313": 7, "fiber": 7, "etias": 4, "rudeus": 12}


def facts(text: str, spec: dict) -> int:
    """A fact is present when every group matches; a group matches when any of its alternatives does."""
    return sum(all(any(re.search(alt, text, re.I) for alt in group) for group in groups) for groups in spec["facts"].values())


def every_tool_was_assented(events: list[dict]) -> bool:
    """§15: every decision in the trace is a pneuma answer. Each tool run must follow a passed RUN or FITS in its round."""
    for tool in (e for e in events if e["kind"] == "tool"):
        ok = any(e["kind"] == "decide" and e.get("what") == "triage" and e["round"] == tool["round"]
                 and any(k.startswith(("tool__", "habit__")) and v["passed"] for k, v in e["answers"].items())
                 for e in events)
        if not ok and "habit" not in tool:
            return False
    return True


def rounds(ev):
    return sum(1 for e in ev if e["kind"] == "decide" and e.get("what") == "triage")


def clean_vault():
    """Questions run against a vault with no notes, habits or fixture files from earlier rows or configurations."""
    for pattern in ("memory/*.md", "habits/*.yaml", "files/sample.txt"):
        for p in (ROOT / "vault").glob(pattern):
            p.unlink()


def run(msg, files=(), withhold=False, isolated=False):
    """isolated: no recent turns, so a question never sees replies from earlier rows or configurations, as the
    full-agent baselines never do."""
    s = load(ROOT)
    turns = loop.recent_turns
    if isolated:
        loop.recent_turns = lambda *a, **k: []
    t = time.perf_counter()
    try:
        out = loop.run(msg, [Path(f) for f in files], loop.Deps(settings=s), withhold_tools=withhold)
    finally:
        loop.recent_turns = turns
    out["seconds"] = round(time.perf_counter() - t, 1)
    out["events"] = read(out["trace"])
    return out


def main() -> int:
    checks = json.loads((ROOT / "bench/checklists.json").read_text(encoding="utf-8"))
    clean_vault()
    rows = []
    for key in ("python313", "fiber", "etias", "rudeus"):
        o = run(checks[key]["query"], isolated=True)
        n = facts(o["reply"], checks[key])
        rows.append((key, o["seconds"], f"{n}/{len(checks[key]['facts'])}", o["seconds"] < LIMITS[key] and n >= FLOORS[key] and every_tool_was_assented(o["events"]), o["trace"].name))
    if "questions" in sys.argv:   # the four questions only, for writer comparisons
        print("\n| row | seconds | result | pass | trace |\n|---|---:|---|---|---|")
        for r in rows:
            print(f"| {r[0]} | {r[1]} | {r[2]} | {'yes' if r[3] else 'NO'} | {r[4]} |")
        return 0
    sample = ROOT / "bench/sample.txt"
    sample.write_text("Dietary fibre keeps digestion regular. Adults need 25 to 38 grams a day.", encoding="utf-8")
    o = run("summarise this file", [sample])
    rows.append(("file", o["seconds"], o["exit"], o["exit"] == "reply" and not any(e["kind"] == "decide" and e.get("what") == "pick" for e in o["events"]), o["trace"].name))
    o = run("which file is that picture from December?")
    rows.append(("picture", o["seconds"], o["exit"], o["exit"] in ("reply", "ask"), o["trace"].name))
    (ROOT / "vault/ops").mkdir(parents=True, exist_ok=True)
    (ROOT / "vault/ops/espn.md").write_text("---\ngoal: win the ESPN fantasy league\nstatus: open\n---\n## notes\ntraded for a kicker\n", encoding="utf-8")
    o = run("research Future Rudeus in Mushoku Tensei")
    g = next((e for e in o["events"] if e["kind"] == "gate"), {})
    rows.append(("operation", o["seconds"], g.get("operation"), g.get("operation") != "espn", o["trace"].name))
    msg = "find the current ETIAS start date and save it as a note"
    for p in (ROOT / "vault/habits").glob("*.yaml"):
        p.unlink()

    def fresh():
        # The four habit runs must take the same path, so the note the previous run wrote is removed each time.
        for p in (ROOT / "vault/memory").glob("*.md"):
            p.unlink()

    fresh()
    o1 = run(msg)
    rows.append(("etias-note-1", o1["seconds"], f"{rounds(o1['events'])} rounds", [e["name"] for e in o1["events"] if e["kind"] == "tool"] == ["digest", "write_note"], o1["trace"].name))
    a1 = accept(o1["trace"], load(ROOT))
    print(a1)
    fresh()
    o2 = run(msg, withhold=True)
    k2 = [e["kind"] for e in o2["events"]]
    blind = all(e.get("blind", True) for e in o2["events"] if e["kind"] == "codex")
    d2 = next((e for e in o2["events"] if e["kind"] == "dispatch"), {})
    work2 = ROOT / "vault" / "work" / o2["trace"].stem
    seen2 = bool(d2.get("files")) and all((work2 / f).is_file() for f in d2["files"])   # the agent's files, where the harness looks
    rows.append(("etias-note-2", o2["seconds"], f"dispatch, files {d2.get('files')}", "dispatch" in k2 and blind and seen2 and o2["exit"] == "reply", o2["trace"].name))
    fresh()
    o3 = run(msg)
    a3 = accept(o3["trace"], load(ROOT))
    print(a3)
    rows.append(("etias-note-3", o3["seconds"], f"promoted={a3['promoted']}", bool(a1["drafted"]) and a3["promoted"] == a1["drafted"], o3["trace"].name))
    fresh()
    o4 = run(msg)
    k4 = [e["kind"] for e in o4["events"]]
    rows.append(("etias-note-4", o4["seconds"], f"{rounds(o4['events'])} rounds", "habit" in k4 and "dispatch" not in k4 and o4["seconds"] < o2["seconds"], o4["trace"].name))
    print("\n| row | seconds | result | pass | trace |\n|---|---:|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {'yes' if r[3] else 'NO'} | {r[4]} |")
    return 0 if all(r[3] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
