"""Splits each benchmark question's list-price cost into Jev, psyche and nous for both configurations."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\| (\S+) \| ([\d.]+) \| (.*?) \| (yes|NO) \| (\S+\.jsonl) \|$")
P = {"jev": (0.042, 0.0), "mercury": (0.04, 0.15), "luna": (1.0, 6.0), "astra": (10.0, 50.0)}

print(f"{'config':16} {'row':10} {'jev':>8} {'psyche':>8} {'nous':>8} {'total':>8}   jev tokens / psyche tokens / nous tokens (in+out)")
for f, label in (("bench/results-codex.txt", "Codex psyche"), ("bench/results-mercury.txt", "Mercury psyche")):
    for line in (ROOT / f).read_text(encoding="utf-8").splitlines():
        m = ROW.match(line.strip())
        if not m or m.group(1) not in ("python313", "fiber", "etias", "rudeus"):
            continue
        c = {"jev": 0.0, "psyche": 0.0, "nous": 0.0}
        t = {"jev": 0, "psyche": 0, "nous": 0}
        for e in (json.loads(l) for l in (ROOT / "traces" / m.group(5)).read_text(encoding="utf-8").splitlines() if l.strip()):
            if e["kind"] == "decide":
                i = (e.get("usage") or {}).get("input_tokens", 0)
                c["jev"] += i * P["jev"][0] / 1e6
                t["jev"] += i
            elif e["kind"] == "codex":
                u = e.get("usage", {})
                model = "astra" if e["tier"][0] == "nous" else ("mercury" if "prompt_tokens" in u else "luna")
                i = u.get("input_tokens") or u.get("prompt_tokens") or 0
                o = u.get("output_tokens") or u.get("completion_tokens") or 0
                part = "nous" if model == "astra" else "psyche"
                c[part] += (i * P[model][0] + o * P[model][1]) / 1e6
                t[part] += i + o
        print(f"{label:16} {m.group(1):10} {c['jev']:8.4f} {c['psyche']:8.4f} {c['nous']:8.4f} {sum(c.values()):8.4f}   {t['jev']:,} / {t['psyche']:,} / {t['nous']:,}")
