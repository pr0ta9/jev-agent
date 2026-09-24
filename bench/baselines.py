"""Runs the four benchmark questions through full agents with their own web search (Codex Sol, Astra and Luna; Claude
Sonnet, Fable and Haiku), each isolated from user configuration in an empty directory, and prints time, tokens and
cost beside Nyx's result files. Facts are scored by hand in hand-scores.json; the regex column is a smoke test.

usage: python bench/baselines.py [sol astra luna sonnet fable haiku]   ("none" refreshes the table only)
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROW = re.compile(r"^\| (\S+) \| ([\d.]+) \| (.*?) \| (yes|NO) \| (\S+\.jsonl) \|$")
PRICES = {"jev": (0.042, 0.0), "mercury": (0.04, 0.15), "luna": (1.0, 6.0), "astra": (10.0, 50.0), "sol": (5.0, 30.0), "sonnet": (3.0, 15.0)}
QUESTIONS = ("python313", "fiber", "etias", "rudeus")
SUFFIX = "\n\nSearch the web as needed and answer fully, with a source URL for each fact."


def facts(text: str, spec: dict) -> int:
    return sum(all(any(re.search(alt, text, re.I) for alt in group) for group in groups) for groups in spec["facts"].values())


def run_sol(query: str) -> dict:
    return run_codex(query, "gpt-5.6-sol", "sol", "Codex Sol")


def run_astra(query: str) -> dict:
    return run_codex(query, "gpt-6-astra", "astra", "Codex Astra")


def run_luna(query: str) -> dict:
    return run_codex(query, "gpt-5.6-luna", "luna", "Codex Luna")


def run_codex(query: str, model: str, price: str, label: str) -> dict:
    exe = shutil.which("codex") or "codex"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:
        cmd = [exe, "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check", "--sandbox", "read-only", "-C", cwd,
               "-m", model, "-c", 'model_reasoning_effort="medium"', "-"]
        proc = subprocess.run(cmd, input=query + SUFFIX, capture_output=True, text=True, encoding="utf-8", timeout=600)
    text, usage, searches = "", {}, 0
    for line in proc.stdout.splitlines():
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text", "")
        if item.get("type") == "web_search":
            searches += 1
        if e.get("type") == "turn.completed":
            usage = e.get("usage", {})
    u = {"in": usage.get("input_tokens", 0), "cached": usage.get("cached_input_tokens", 0), "out": usage.get("output_tokens", 0)}
    return {"agent": label, "seconds": round(time.perf_counter() - started, 1), "text": text, "searches": searches, "usage": u,
            "cost": (u["in"] * PRICES[price][0] + u["out"] * PRICES[price][1]) / 1e6, "calls": 1}


def run_sonnet(query: str) -> dict:
    return run_claude(query, "sonnet", "Claude Sonnet")


def run_fable(query: str) -> dict:
    return run_claude(query, "fable", "Claude Fable")


def run_haiku(query: str) -> dict:
    # Haiku in Claude Code refused the fiber and Rudeus questions as outside software engineering (2026-09-23).
    return run_claude(query, "haiku", "Claude Haiku", ["--append-system-prompt", "You are also a general research assistant: answer any question."])


def run_claude(query: str, model: str, label: str, extra: list[str] = ()) -> dict:
    exe = shutil.which("claude.cmd") or shutil.which("claude") or "claude"
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as cwd:   # claude leaves a lock file open briefly
        # Only local settings (none in an empty directory) and no MCP servers: the user's CLAUDE.md, memory and plugins
        # stay out; verified 2026-09-22 by asking the model what it sees. --bare would also work but needs an API key.
        cmd = [exe, "-p", "--model", model, "--output-format", "json", "--setting-sources", "local", "--strict-mcp-config",
               "--allowedTools", "WebSearch,WebFetch", *extra, "--", query + SUFFIX]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=600, cwd=cwd, env=env)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {"result": proc.stdout[-2000:], "usage": {}, "total_cost_usd": 0.0, "num_turns": 0}
    usage = data.get("usage", {})
    u = {"in": usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0) + usage.get("cache_creation_input_tokens", 0),
         "cached": usage.get("cache_read_input_tokens", 0), "out": usage.get("output_tokens", 0)}
    searches = (usage.get("server_tool_use") or {}).get("web_search_requests", 0) + (usage.get("server_tool_use") or {}).get("web_fetch_requests", 0)
    return {"agent": label, "seconds": round(time.perf_counter() - started, 1), "text": data.get("result", ""), "searches": searches,
            "usage": u, "cost": data.get("total_cost_usd", 0.0), "calls": data.get("num_turns", 0), "raw_usage": usage}


def ours(results: Path, label: str) -> dict:
    nous = "sol" if "Sol" in label else "astra"
    out = {}
    for line in results.read_text(encoding="utf-8").splitlines():
        m = ROW.match(line.strip())
        if not m or m.group(1) not in QUESTIONS:
            continue
        ev = [json.loads(l) for l in (ROOT / "traces" / m.group(5)).read_text(encoding="utf-8").splitlines() if l.strip()]
        u = {"in": 0, "cached": 0, "out": 0}
        cost, calls, searches = 0.0, 0, 0
        for e in ev:
            if e["kind"] == "decide":
                jin = (e.get("usage") or {}).get("input_tokens", 0)
                u["in"] += jin
                cost += jin * PRICES["jev"][0] / 1e6
                calls += 1
            elif e["kind"] == "codex":
                w = e.get("usage", {})
                model = nous if e["tier"][0] == "nous" else ("mercury" if "prompt_tokens" in w else "luna")
                i, c, o = w.get("input_tokens") or w.get("prompt_tokens") or 0, w.get("cached_input_tokens") or 0, w.get("output_tokens") or w.get("completion_tokens") or 0
                u["in"] += i; u["cached"] += c; u["out"] += o
                cost += (i * PRICES[model][0] + o * PRICES[model][1]) / 1e6
                calls += 1
            elif e["kind"] == "tool" and e["name"] == "digest":
                searches += 1
        reply = [e for e in ev if e["kind"] == "reply"][-1]["text"]
        out[m.group(1)] = {"agent": label, "seconds": float(m.group(2)), "text": reply, "searches": searches, "usage": u, "cost": cost, "calls": calls}
    return out


def main() -> int:
    checks = json.loads((ROOT / "bench/checklists.json").read_text(encoding="utf-8"))
    only = set(sys.argv[1:])
    previous = json.loads((ROOT / "bench/baselines.json").read_text(encoding="utf-8")) if (ROOT / "bench/baselines.json").exists() else {}
    runs = dict(previous)   # keeps reference entries added by hand, such as Google AI Mode
    for a in ("Codex Sol", "Codex Astra", "Codex Luna", "Claude Sonnet", "Claude Fable", "Claude Haiku"):
        runs.setdefault(a, {})
    for key in QUESTIONS:
        q = checks[key]["query"]
        for label, fn in (("Codex Sol", run_sol), ("Codex Astra", run_astra), ("Codex Luna", run_luna),
                          ("Claude Sonnet", run_sonnet), ("Claude Fable", run_fable), ("Claude Haiku", run_haiku)):
            if only and label.split()[-1].lower() not in only:
                continue
            r = fn(q)
            r["facts"] = f"{facts(r['text'], checks[key])}/{len(checks[key]['facts'])}"
            runs[label][key] = r
            print(label, key, r["seconds"], "s", r["facts"], file=sys.stderr)
    for label, path in (("Nyx, Codex psyche", "results-codex.txt"), ("Nyx, Mercury psyche", "results-mercury.txt"),
                        ("Nyx, Mercury psyche, nous Sol", "results-mercury-sol.txt"), ("Nyx, Mercury writes all", "results-mercury-all.txt"),
                        ("Nyx new digest, Mercury + Astra", "results-nd-mercury-astra.txt"),
                        ("Nyx new digest, Mercury + Sol", "results-nd-mercury-sol.txt"),
                        ("Nyx new digest, Mercury writes all", "results-nd-mercury-all.txt"),
                        ("Nyx release, Mercury + Astra", "results-rel-mercury-astra.txt"),
                        ("Nyx release, Mercury + Sol", "results-rel-mercury-sol.txt"),
                        ("Nyx release, Mercury writes all, run 1", "results-rel-mercury-all1.txt"),
                        ("Nyx release, Mercury writes all, run 2", "results-rel-mercury-all2.txt"),
                        ("Nyx release, Mercury writes all, run 3", "results-rel-mercury-all3.txt")):
        if (ROOT / "bench" / path).exists():
            runs[label] = ours(ROOT / "bench" / path, label)
            for key, r in runs[label].items():
                r["facts"] = f"{facts(r['text'], checks[key])}/{len(checks[key]['facts'])}"
    (ROOT / "bench/baselines.json").write_text(json.dumps(runs, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n| question | agent | seconds | facts | model calls | searches | tokens in (cached) | out | cost at list |\n|---|---|---:|---|---:|---:|---:|---:|---:|")
    for key in QUESTIONS:
        for label in runs:
            r = runs[label].get(key)
            if r:
                print(f"| {key} | {label} | {r['seconds']} | {r['facts']} | {r['calls']} | {r['searches']} | {r['usage']['in']:,} ({r['usage']['cached']:,}) | {r['usage']['out']:,} | ${r['cost']:.3f} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
