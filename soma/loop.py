"""The round. Code owns control flow, budgets and side effects; pneuma answers; writers write."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import nous
from . import questions as Q
from . import tools
from .codex import run_codex
from .gate import gate
from .ladder import fill
from .learn import replay
from .pneuma import Pneuma
from .psyche import Psyche
from .settings import Settings
from .state import Fragment, Result, State, fold
from .trace import Trace, new_trace, recent_turns
from .vault import Vault


@dataclass
class Deps:
    settings: Settings
    pneuma_post: Callable | None = None
    codex: Callable = run_codex
    vault: Vault | None = None
    pneuma: Pneuma | None = None
    psyche: Psyche | None = None
    trace: Trace | None = None

    def ready(self) -> "Deps":
        self.vault = self.vault or Vault(self.settings.vault)
        self.trace = self.trace or new_trace(self.settings.traces)
        self.pneuma = self.pneuma or Pneuma(self.settings, post=self.pneuma_post, trace=self.trace)
        self.psyche = self.psyche or Psyche(self.settings, codex=self.codex, trace=self.trace)
        return self


def run(message: str, files: list[Path], deps: Deps, withhold_tools: bool = False) -> dict:
    d = deps.ready()
    state = State(message=message, turns=recent_turns(d.settings.traces), withhold_tools=withhold_tools)
    state.attachments = [d.vault.add_file(Path(f)) for f in files]
    d.trace.write("message", text=message, files=[str(f) for f in files])
    fetch(state, d)
    gate(state, d)
    while state.round < d.settings.max_rounds and _round(state, d):
        pass
    exit_, text = present(state, d)
    d.trace.write("reply", exit=exit_, text=text, rounds=state.round)
    if state.operation:
        d.vault.note_op(state.operation["id"], text[:200] or f"[{exit_}]")
    return {"exit": exit_, "reply": text, "trace": d.trace.path}


def fetch(state: State, d: Deps) -> None:
    d.vault.index()
    state.fragments = d.vault.fetch(state.message)
    for h in d.vault.habits("promoted"):
        state.fragments.append(Fragment(f"habit/{h['id']}", "habit", h["id"], " · ".join(h.get("trigger", [])), f"habits/{h['id']}.yaml", {"habit": h}))
    state.fragments += [Fragment(f"turn/{i}", "turn", t["role"], t["text"][:600], "traces") for i, t in enumerate(state.turns)]
    state.turns = []
    d.trace.write("fetch", fragments=[f.id for f in state.fragments])


def _round(state: State, d: Deps) -> bool:
    state.round += 1
    view = state.view()
    habits = [f.meta["habit"] for f in state.fragments_of("habit")]
    tool_names = [] if state.withhold_tools else [{"name": n, "snippet": c["snippet"]} for n, c in tools.CATALOG.items()]
    p = state.last_prose()
    facts = [f for r in state.results if r.kind == "tool" and isinstance(r.output, dict) for f in r.output.get("facts", [])]
    pending = None if p is None or p.verified else {"text": p.output, "points": p.points, "facts": facts}
    if pending and d.settings.expect:   # once per request: an expert's checklist, since the digest's aspects cannot show what it never fetched
        state.expected = d.psyche.expect(state.message) if state.expected is None else state.expected
        pending["expected"] = state.expected
    q, th = Q.triage_questions(view, habits, tool_names, pending, state.fragments if state.round == 1 else [], d.settings)
    a = d.pneuma.decide(view, q, th, state.round)
    if a is None:
        return _ask(state, "I lost the thread. Say it again?", ["say it again"], state.round)
    if state.round == 1:
        state.kept = [f.id for f in state.fragments if a.get(f"frag__{f.id}") is None or a[f"frag__{f.id}"].choice == "KEEP"]
        state.turns = [{"role": f.title, "text": f.text} for f in state.kept_fragments() if f.kind == "turn"]
    state.subject_named = a["subject"].choice == "NAMED" and a["subject"].passed
    covered = {pt for r in state.results if r.kind == "tool" for pt in r.points}
    has_sources = any(r.kind in ("tool", "habit") for r in state.results)
    if pending:
        verdict = Q.verify_pending(a, pending["points"], covered)
        state.need = verdict["fetch"]
        dropped = [] if verdict["fetch"] else Q.missing_facts(a, pending["facts"])
        unmet = [] if verdict["fetch"] else Q.unmet(a, pending.get("expected", []))
        if (verdict["rewrite"] or dropped or unmet) and _rewrite(state, d, verdict["rewrite"], dropped, a, unmet):
            return True
        if not verdict["fetch"]:
            state.last_prose().verified = True
    last = state.last_prose()
    if last and any(r.kind == "tool" and r.round > last.round for r in state.results):
        last = None   # a prose written before a later tool result is stale; it neither ends the request nor is presented
    if Q.is_done(a, verified=last is not None and last.verified, has_points=bool(last and last.points)):
        return False
    needs_sources = tuple(n for n, c in tools.CATALOG.items() if "prose" in c["slots"].values())
    needs_file = tuple(n for n, c in tools.CATALOG.items() if "file" in c["slots"].values())
    actions = Q.actions_from(a, state, points_covered=has_sources, available=tuple(t["name"] for t in tool_names), needs_sources=needs_sources, needs_file=needs_file)
    if not actions:
        return _no_move(state, d, a)   # no runnable action is a no-move, even when a guard dropped the only tool pneuma passed
    with ThreadPoolExecutor(max_workers=len(actions)) as pool:
        results = [r for r in pool.map(lambda act: _run_action(act, state, d, a), actions) if r is not None]
    if results and all(r.kind == "drop" for r in results):
        return _no_move(state, d, a) if not has_sources else bool(fold(state, [_write(state, d, Q.prose_tier(a, d.settings.nous_scope))]))
    fold(state, results)
    if any(r.kind == "habit" or (r.kind == "tool" and r.name in needs_sources) for r in results):
        return False   # a habit is the whole workflow, and a written note is the answer; either would repeat every round
    return state.ask is None


def _run_action(act: Q.Action, state: State, d: Deps, a) -> Result | None:
    if act.kind == "prose":
        return _write(state, d, Q.prose_tier(a, d.settings.nous_scope))
    if act.kind == "habit":
        return replay(act.name, state, d)
    name = act.name
    slots = {}
    for slot, slot_type in tools.CATALOG[name]["slots"].items():
        if slot_type == "prose":
            slots[slot] = _write(state, d, Q.prose_tier(a, d.settings.nous_scope), request=f"{state.message}\n\nWrite the `{slot}` for tool `{name}`.").output
            continue
        proposed = act.slots.get(slot)
        value = fill(slot, slot_type, state, d, proposed if proposed not in (None, "?") else None)
        if isinstance(value, dict):
            return Result("ask", "ladder", {"slot": slot}, value, state.round)
        slots[slot] = value
    if any(r.kind == "tool" and r.name == name and r.slots == slots for r in state.results):
        return Result("drop", name, slots, None, state.round)   # identical inputs already ran; repeating them also trips SearXNG
    result = tools.run(name, slots, d.settings, d.vault, state.round)
    text = (result.output.get("text", "") if isinstance(result.output, dict) else str(result.output))[:2000]
    filled = {s: state.filled_by.get(s, "written") for s in slots}
    d.trace.write("tool", name=name, slots=slots, filled=filled, output=str(result.output)[:500], text=text, points=result.points, round=state.round)
    if name == "digest" and result.output.get("error"):   # the same query would only be dropped as a repeat; say so instead
        return Result("ask", "digest", slots, {"question": "The web search came back empty; the search engines may be rate-limited. Try again?",
                                                "options": ["try again", "never mind"]}, state.round)
    return result


def _write(state: State, d: Deps, tier: tuple, request: str | None = None, dropped: list[dict] = ()) -> Result:
    tool_results = [r for r in state.results if r.kind == "tool"]
    source_steps = [i for i, r in enumerate(tool_results) if isinstance(r.output, dict) and r.output.get("text")]
    sources = [f"{tool_results[i].name}: {tool_results[i].output['text']}" for i in source_steps]
    sources += [f"{f.title}: {f.text}" for f in state.kept_fragments()]
    points = sorted({pt for r in tool_results for pt in r.points}) or [f"addresses {x.name}" for x in state.attachments]
    text = d.psyche.write(request or state.message, sources, points + [f"state what {f['site']} says: {f['text']}" for f in dropped], tier)
    d.trace.write("prose", tier=list(tier), points=points, sources=source_steps, dropped=len(dropped), chars=len(text), text=text[:4000], round=state.round)
    return Result("prose", "write", {}, text, state.round, points=points, tier=tier, sources=source_steps)


def _rewrite(state: State, d: Deps, missing: list[str], dropped: list[dict] = (), a=None, unmet: list[str] = ()) -> bool:
    last = state.last_prose()
    agent_wrote = last.name == "dispatch"   # a dispatched agent's answer is not rewritten, and a request dispatches once
    first = not agent_wrote and not any(r.kind == "prose" and r.tier != last.tier for r in state.results)
    nxt = Q.escalate(last.tier) if first else None
    if nxt and nxt[0] == "nous" and d.settings.nous_scope == "planning":
        nxt = None
    digests = "\n".join(r.output.get("text", "") for r in state.results if r.kind == "tool" and r.name == "digest")
    settled = bool(missing) and all(Q.conflicted(digests, point) for point in missing)
    if settled:
        nxt = None   # the sources disagree on every missing point; no rewrite can settle that
    first = not agent_wrote and sum(r.kind == "prose" for r in state.results) == 1
    if dropped and first and (nxt is None or not missing):
        nxt = last.tier   # the writer had the dropped passages: the same tier told which is the cheaper fix, once
    elif not missing:
        nxt = None
    new = _write(state, d, nxt, dropped=dropped) if nxt else None
    if new is None or not new.output.strip():   # an empty rewrite (a discarded non-blind session) keeps the draft
        gaps = ([] if settled else list(missing)) + list(unmet)   # unmet expectations go to the agent but are never footnoted
        if gaps and not agent_wrote and Q.researchable(a) and _dispatch(state, d, a, last.output, gaps, last.points):
            return True
        if missing:
            last.output = f"{last.output}\n\nNot covered by the sources: {', '.join(missing)}."
        last.verified = True
        return False
    fold(state, [new])
    return True


def _no_move(state: State, d: Deps, a) -> bool:
    if any(r.name == "dispatch" for r in state.results):   # one dispatch per request; a second no-move is the user's call
        return _ask(state, "I do not have a sure move for that. Which is closest?", ["rephrase it", "give me a file", "never mind"], state.round)
    return _dispatch(state, d, a)


def _dispatch(state: State, d: Deps, a, draft: str = "", missing: list[str] = (), points: list[str] = ()) -> bool:
    external = bool(a and a.get("exposure") and a["exposure"].choice == "EXTERNAL" and a["exposure"].passed)
    got = nous.dispatch(state, d.settings, d.settings.vault / "work" / d.trace.path.stem, d.codex, d.trace, draft, missing, points, external)
    fold(state, got[:1] if draft and got[-1].kind == "ask" else got)   # an agent that fails after a failed check leaves the draft standing
    return got[-1].kind == "prose"


def _ask(state: State, question: str, options: list[str], round_no: int) -> bool:
    fold(state, [Result("ask", "loop", {}, {"question": question, "options": options}, round_no)])
    return False


def present(state: State, d: Deps) -> tuple[str, str]:
    if state.ask:
        return "ask", d.psyche.render(state, "ask", state.ask["question"], options=state.ask["options"])
    prose = state.last_prose()
    texts = [r for r in state.results_of("tool") if isinstance(r.output, dict) and r.output.get("text")]
    if prose and prose.output and (not texts or prose.round >= texts[-1].round):   # a prose older than the last tool result is stale
        return "reply", d.psyche.render(state, "reply", prose.output)
    if texts:
        return "reply", d.psyche.render(state, "reply", texts[-1].output["text"][:2000])
    return "end", ""
