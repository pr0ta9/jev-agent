"""Every question the loop asks, and what code does with the answers. Nothing decides outside this file."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .pneuma import Answer, choice
from .settings import Settings
from .state import State

YES_NO = {"YES": "Yes.", "NO": "No."}
ESCALATION = [("psyche", "low"), ("psyche", "high"), ("nous", "medium"), ("nous", "high")]
_FILL = {("WORDS", "INTERNAL"): 0, ("WORDS", "VISIBLE"): 0, ("WORDS", "EXTERNAL"): 1,
         ("ONE", "INTERNAL"): 0, ("ONE", "VISIBLE"): 1, ("ONE", "EXTERNAL"): 2,
         ("SEVERAL", "INTERNAL"): 1, ("SEVERAL", "VISIBLE"): 2, ("SEVERAL", "EXTERNAL"): 3}


@dataclass
class Action:
    kind: str                 # "habit" | "tool" | "prose"
    name: str
    slots: dict = field(default_factory=dict)
    tier: tuple | None = None


def fill_table(reach: str, exposure: str) -> tuple:
    return ESCALATION[_FILL.get((reach, exposure), 0)]


def escalate(tier: tuple) -> tuple | None:
    i = ESCALATION.index(tuple(tier))
    return ESCALATION[i + 1] if i + 1 < len(ESCALATION) else None


def gate_questions(view: dict, ops: list[dict], settings: Settings):
    th = settings.thresholds
    view["operations"] = [{"id": o["id"], "goal": o["goal"], "status": o["status"], "latest_note": o.get("note", "")} for o in ops]
    q, t = {}, {}
    for o in ops:
        q[f"op__{o['id']}"] = choice(f"Does `message` continue operation `{o['id']}` (see `operations`: its goal and latest note)? Only a clear continuation of that goal counts.", YES_NO)
        t[f"op__{o['id']}"] = th["attach"]
    q["outlives"] = choice("Will satisfying `message` take work beyond this one exchange, so that it should become a long-lived operation with its own notes?", YES_NO)
    t["outlives"] = th["outlives"]
    return q, t


def triage_questions(view: dict, habits: list[dict], tools: list[str], pending, fragments: list, settings: Settings):
    th = settings.thresholds
    q, t = {}, {}
    if fragments:
        view["fragments"] = [{"id": f.id, "kind": f.kind, "title": f.title, "text": f.text[:300]} for f in fragments]
        for f in fragments:
            q[f"frag__{f.id}"] = choice(f"Does answering `message` need fragment `{f.id}` (see `fragments`)?", {"KEEP": "It bears on the message.", "DROP": "It does not."})
            t[f"frag__{f.id}"] = th["fetch"]
    view["habits"] = [{"id": h["id"], "trigger": h.get("trigger", [])} for h in habits]
    for h in habits:
        q[f"habit__{h['id']}"] = choice(f"Does habit `{h['id']}` (see `habits`, its trigger phrases) fit `message` closely enough to replay as-is?", {"FITS": "The habit does what the message asks.", "NO": "It does not."})
        t[f"habit__{h['id']}"] = th["habit"]
    catalog = [{"name": x, "snippet": ""} if isinstance(x, str) else x for x in tools]
    view["tools"] = catalog
    for tool in catalog:
        name = tool["name"]
        q[f"tool__{name}"] = choice(f"Should tool `{name}` (see `tools` for what it does) run now to satisfy `message`, given `results` so far? Run it if the message needs what it produces and its inputs can be filled from the message, attachments or results.", {"RUN": "Run it now.", "NO": "Not now."})
        t[f"tool__{name}"] = th["tool"]
    # Wording measured 2026-09-22 (bench/probe_need.py): saying that general knowledge does not count lifted WEB from
    # 0.57 to 0.93 on a Python question judged with unrelated turns in view.
    q["need"] = choice("Given `results` so far, what does `message` still need before text can be written for the user?", {
        "STATE": "Nothing more to fetch: it is conversation or opinion, or the facts it needs are already in `kept` or `results`. General knowledge does not count: the writers may only state facts that are in state.",
        "WEB": "Factual content that a web search must still fetch, including things a well-read person would know, because it is not in `results` yet.",
        "VAULT": "A file or note from the vault, named or referred to in the message.",
        "WRITE": "A note or file to be written from facts that are already in `results`. If those facts are not in `results` yet, choose WEB or VAULT instead."})
    t["need"] = th["tool"]
    q["prose"] = choice("Does satisfying `message` at this point require writing text (a reply, a note, a summary), as opposed to running a tool first?", {"NEEDED": "Text must be written now.", "NO": "Not yet, or not at all."})
    t["prose"] = th["prose"]
    q["reach"] = choice("If text is written, how much must it reconcile?", {"WORDS": "Only the user's own words.", "ONE": "One thing in `kept` or `results`.", "SEVERAL": "Several things in `kept` or `results`."})
    q["exposure"] = choice("If text is written, who sees it and can it be taken back?", {"INTERNAL": "Internal, a query or a name.", "VISIBLE": "The user sees it, a reply or a note.", "EXTERNAL": "It leaves the system or cannot be undone."})
    q["subject"] = choice("Does `message` itself name the subject it is about (a thing, person, place or topic), rather than referring to it indirectly?", {"NAMED": "The subject is named in the message.", "NO": "It is not."})
    t["subject"] = th["subject"]
    q["satisfied"] = choice("Is `message` fully satisfied by what is in `results` now, so that nothing remains but to present it?", YES_NO)
    t["satisfied"] = th["stop"]
    if pending:
        view["text"], view["points"] = pending["text"], pending["points"]
        for i, point in enumerate(pending["points"]):
            q[f"point__{i}"] = choice(f"Does `text` address point {i}, `{point}` (see `points`), with concrete content?", {"PRESENT": "Fully.", "PARTIAL": "Partly or vaguely.", "ABSENT": "Not at all."})
        q["research"] = choice("If `text` leaves any point in `points` partly or wholly unanswered, could more web research answer it, as opposed to the sources simply not recording it?",
                               {"YES": "More research could answer it.", "NO": "Nothing more could be found, or nothing is missing."})
        t["research"] = th["tool"]
        view["expected"] = pending.get("expected", [])
        for k in range(len(view["expected"])):
            q[f"expect__{k}"] = choice(f"Does `text` give the specific answer to `expected[{k}]`, naming the concrete thing asked for (a flag, a number, a name, a cause), not only its general topic?",
                                       {"ANSWERED": "Yes, it names the specific answer.", "MISSING": "No, or only the general topic, and the request calls for it.", "NOT_NEEDED": "The request does not call for it."})
        view["facts"] = [f"{f['site']} on {f['aspect']}: {f['text']}" for f in pending.get("facts", [])]
        for j in range(len(view["facts"])):
            q[f"fact__{j}"] = choice(f"Does `text` state what passage {j} in `facts` says in answer to the question, in any words?",
                                     {"STATED": "Yes, or the passage adds nothing the question asks for.", "MISSING": "The passage answers part of the question and `text` leaves it out."})
    return q, t


def researchable(a: dict[str, Answer] | None) -> bool:
    return bool(a) and _passed(a, "research", "YES")


def unmet(a: dict[str, Answer], expected: list[str]) -> list[str]:
    return [e for k, e in enumerate(expected) if _passed(a, f"expect__{k}", "MISSING")]


def missing_facts(a: dict[str, Answer], facts: list[dict]) -> list[dict]:
    return [f for j, f in enumerate(facts) if _passed(a, f"fact__{j}", "MISSING")]


def ladder_questions(slot: str, need: str, candidates: list[str]):
    # One yes/no per candidate, never one Choice over all of them: forty near-equivalent options split the
    # probability mass so that nothing reaches the gate (measured 2026-09-22; §9.5 used per-candidate judgments).
    q = {f"cand__{i}": choice(f"Does candidate `cand__{i}` (see `candidates`), \"{c}\", fill slot `{slot}` for the need `{need}`, given `message`?",
                              {"FITS": "It fills the slot well.", "NO": "It does not, or another candidate is clearly better."})
         for i, c in enumerate(candidates)}
    return q, {k: 0.7 for k in q}


def _passed(a: dict[str, Answer], key: str, value: str) -> bool:
    return key in a and a[key].choice == value and a[key].passed


def prose_runnable(a: dict[str, Answer], points_covered: bool) -> bool:
    # With a source in state, writing is the only move left once no tool or habit fits; otherwise the loop
    # re-plans the same fetch forever. Writing from the user's words alone needs a confident "nothing more is
    # needed": "reach: words" alone let fact questions be answered from nothing (measured 2026-09-22).
    if points_covered:
        return True
    return _passed(a, "prose", "NEEDED") and _passed(a, "need", "STATE")


def no_move(a: dict[str, Answer], points_covered: bool) -> bool:
    return (not any(_passed(a, k, "FITS") for k in a if k.startswith("habit__"))
            and not any(_passed(a, k, "RUN") for k in a if k.startswith("tool__"))
            and not prose_runnable(a, points_covered))


def is_done(a: dict[str, Answer], verified: bool = False, has_points: bool = True) -> bool:
    # A prose that passed every point ends the request; "satisfied" at 0.85 alone rarely does, and re-writing is
    # the most expensive thing the loop can do. A prose with no points had nothing to verify, so it ends the
    # request unless pneuma is confident the request is not satisfied. Neither ends it while pneuma passes a tool run:
    # a verified reply to "find X and save it as a note" still has the note to write.
    if verified:
        return (has_points or not _passed(a, "satisfied", "NO")) and not any(_passed(a, k, "RUN") for k in a if k.startswith("tool__"))
    return _passed(a, "satisfied", "YES") and all(v.choice == "PRESENT" for k, v in a.items() if k.startswith("point__"))


def verify_pending(a: dict[str, Answer], points: list[str], covered: set[str]) -> dict:
    fetch, rewrite = [], []
    for i, point in enumerate(points):
        c = a.get(f"point__{i}")
        if c is None or c.choice == "PRESENT":
            continue
        (rewrite if point in covered else fetch).append(point)
    return {"fetch": fetch, "rewrite": rewrite}


def conflicted(digest: str, point: str) -> bool:
    """The digest labels a disagreeing passage with its aspect key; no rewrite can settle a point the sources disagree on."""
    topics = digest.split("Topics: ", 1)[-1].split("\n", 1)[0]
    key = re.search(r"(\w+): " + re.escape(point) + r"(?:;|$)", topics)
    return bool(key) and f"; {key.group(1)}; possible disagreement]" in digest


def prose_tier(a: dict[str, Answer], nous_scope: str = "all") -> tuple:
    reach, exposure = a["reach"], a["exposure"]
    tier = ESCALATION[0] if reach.confidence < 0.5 or exposure.confidence < 0.5 else fill_table(reach.choice, exposure.choice)
    if nous_scope == "planning" and tier[0] == "nous":
        return ("psyche", "high")   # psyche writes everything; nous is only ever dispatched as an agent
    return tier


def actions_from(a: dict[str, Answer], state: State, points_covered: bool = False, available: tuple = (), needs_sources: tuple = (), needs_file: tuple = ()) -> list[Action]:
    habits = [Action("habit", k[len("habit__"):]) for k in a if k.startswith("habit__") and _passed(a, k, "FITS")]
    if habits:
        return habits[:1]
    tools = [Action("tool", k[len("tool__"):]) for k in a if k.startswith("tool__") and _passed(a, k, "RUN")]
    # The `need` Choice is the sharper question; it adds the one tool its answer implies when no per-tool answer did.
    for need, tool in (("WEB", "digest"), ("VAULT", "read_file"), ("WRITE", "write_note")):
        if _passed(a, "need", need) and tool in available and tool not in {x.name for x in tools} and not any(r.name == tool for r in state.results):
            tools.append(Action("tool", tool))
    if not points_covered:
        tools = [x for x in tools if x.name not in needs_sources]   # a tool that writes prose waits for something to write from
    if not state.attachments and not _passed(a, "need", "VAULT"):
        tools = [x for x in tools if x.name not in needs_file]      # a file tool needs an attachment or a confident VAULT answer
    if tools:
        return tools
    if prose_runnable(a, points_covered):
        return [Action("prose", "write", tier=prose_tier(a))]
    return []
