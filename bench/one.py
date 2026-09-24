"""Runs one benchmark question and prints the result row. usage: python bench/one.py <key>"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bench.run import clean_vault, run, facts, every_tool_was_assented, LIMITS, FLOORS, ROOT
key = sys.argv[1]
checks = json.loads((ROOT / "bench/checklists.json").read_text(encoding="utf-8"))
clean_vault()
o = run(checks[key]["query"], isolated=True)
n = facts(o["reply"], checks[key])
ok = o["seconds"] < LIMITS[key] and n >= FLOORS[key] and every_tool_was_assented(o["events"])
print(f"| {key} | {o['seconds']} | {n}/{len(checks[key]['facts'])} | {'yes' if ok else 'NO'} | {o['trace'].name} |")
