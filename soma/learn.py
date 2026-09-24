"""Runs on --accept, never in the foreground: verify a pending draft against this trace, then draft from it."""
from __future__ import annotations

import re
from pathlib import Path

import yaml

from . import tools
from .codex import run_codex
from .settings import Settings
from .state import Result, State, fold
from .trace import read
from .vault import Vault


def resolve_binding(binding: dict, message: str, results: list):
    if "literal" in binding:
        return binding["literal"]
    if "span" in binding:
        return binding["span"] if binding["span"].lower() in message.lower() else binding["span"]
    if "step" in binding:
        out = results[binding["step"]]["output"] if binding["step"] < len(results) else ""
        return out.get("text", "") if isinstance(out, dict) else str(out)
    if "prose" in binding:
        p = binding["prose"]
        return {"tier": tuple(p["tier"]), "sources": [resolve_binding({"step": i}, message, results) for i in p.get("sources", [])]}
    raise ValueError(f"unknown binding {binding}")


def _calls(events: list[dict]) -> tuple[str, list[dict]]:
    message = next(e["text"] for e in events if e["kind"] == "message")
    calls, last_prose = [], None
    for e in events:
        if e["kind"] == "prose":
            last_prose = e
        if e["kind"] == "tool":
            calls.append({"tool": e["name"], "slots": e["slots"], "filled": e.get("filled", {}), "output": {"text": e.get("text", "")}, "prose": last_prose})
            last_prose = None
    return message, calls


def replay(habit_id: str, state: State, d) -> Result:
    """Run a promoted habit: bindings resolve, prose slots are written, no model decides a step."""
    habit = next(f.meta["habit"] for f in state.fragments_of("habit") if f.meta["habit"]["id"] == habit_id)
    prior: list[dict] = []
    for step in habit["steps"]:
        slots = {}
        for slot, binding in step["slots"].items():
            value = resolve_binding(binding, state.message, prior)
            if isinstance(value, dict):
                value = d.psyche.write(state.message, value["sources"], [], value["tier"])
            slots[slot] = value
        r = tools.run(step["tool"], slots, d.settings, d.vault, state.round)
        text = (r.output.get("text", "") if isinstance(r.output, dict) else str(r.output))[:2000]
        d.trace.write("tool", name=step["tool"], slots=slots, output=str(r.output)[:500], text=text, points=r.points, round=state.round, habit=habit_id)
        prior.append({"output": r.output})
        fold(state, [r])
    d.trace.write("habit", id=habit_id, steps=len(habit["steps"]), round=state.round)
    return Result("habit", habit_id, {}, prior[-1]["output"] if prior else None, state.round)


def _matches(habit: dict, message: str) -> bool:
    words = set(re.findall(r"\w+", message.lower()))
    return any(len(words & set(re.findall(r"\w+", t.lower()))) / max(1, len(set(re.findall(r"\w+", t.lower())))) >= 0.5 for t in habit.get("trigger", []))


def _reproduces(habit: dict, message: str, calls: list[dict]) -> bool:
    if len(habit["steps"]) != len(calls):
        return False
    for i, (step, call) in enumerate(zip(habit["steps"], calls)):
        if step["tool"] != call["tool"] or set(step["slots"]) != set(call["slots"]):
            return False
        for slot, binding in step["slots"].items():
            if "prose" in binding:
                # The tier is pneuma's momentary choice from reach and exposure; the sources are the workflow.
                if list(binding["prose"].get("sources", [])) != list((call.get("prose") or {}).get("sources", [])):
                    return False
            elif resolve_binding(binding, message, calls[:i]) != call["slots"][slot]:
                # A value the free run got from a generator proposal never repeats verbatim, whatever the binding kind;
                # the habit's own binding is what replays. Only values taken from the message or a step must match.
                if call.get("filled", {}).get(slot) in ("proposed", "plan"):
                    continue
                return False
    return True


def _draft(events: list[dict], settings: Settings, codex) -> dict | None:
    template = (settings.prompts / "habit.md").read_text(encoding="utf-8")
    lines = "\n".join(f"{e['kind']}: " + ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("t", "kind")) for e in events)
    res = codex(settings.nous_model, "medium", template.replace("{{trace}}", lines[:12000]), settings)
    if not res.blind:
        return None
    try:
        habit = yaml.safe_load(res.text.strip("` \n").removeprefix("yaml").strip()) or {}
    except yaml.YAMLError:
        return None
    if not (isinstance(habit, dict) and habit.get("id") and isinstance(habit.get("steps"), list) and isinstance(habit.get("trigger"), list)):
        return None
    if not all(isinstance(s, dict) and s.get("tool") in tools.CATALOG and isinstance(s.get("slots"), dict) for s in habit["steps"]):
        return None
    habit["status"] = "draft"
    return habit


def accept(trace_path: Path, settings: Settings, codex=run_codex) -> dict:
    vault = Vault(settings.vault)
    events = read(trace_path)
    message, calls = _calls(events)
    out = {"trace": str(trace_path), "promoted": None, "retired": None, "drafted": None}
    if any(e["kind"] == "dispatch" for e in events):   # an agent session is not a replayable workflow: it neither verifies nor drafts
        return out
    for habit in vault.habits("draft"):
        if not _matches(habit, message):
            continue
        habit["status"] = "promoted" if _reproduces(habit, message, calls) else "retired"
        vault.save_habit(habit)
        out["promoted" if habit["status"] == "promoted" else "retired"] = habit["id"]
    if out["promoted"] or any(_matches(h, message) for h in vault.habits("promoted")):
        return out
    draft = _draft(events, settings, codex)
    if draft:
        vault.save_habit(draft)
        out["drafted"] = draft["id"]
    return out
