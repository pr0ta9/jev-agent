"""Fill one slot: attachments, the user's words and spans, autocomplete on every span, the resolver, proposals, ask."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

import httpx

from . import questions as Q
from .state import State

MONTHS = {m: i + 1 for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"])}
IMAGE_WORDS = ("picture", "photo", "image", "screenshot")
_QUOTED = re.compile(r'"([^"]{2,80})"|“([^”]{2,80})”')
_CAPS = re.compile(r"\b(?:[A-Z][\w-]+(?:\s+[A-Z][\w-]+)*)\b")
_DATES = re.compile(r"\b(?:\d{1,2}\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December)(?:\s+\d{4})?\b|\b\d{4}\b")
_CJK = re.compile(r"[一-鿿]{2,}")


def spans(state: State, cap: int = 8) -> list[str]:
    m = state.message
    found = [a or b for a, b in _QUOTED.findall(m)] + _DATES.findall(m) + _CAPS.findall(m) + _CJK.findall(m)
    found += [a.name for a in state.attachments] + [f.title for f in state.kept_fragments()]
    out: list[str] = []
    for s in found:
        s = s.strip()
        if s and s.lower() not in {x.lower() for x in out} and len(s) > 1:
            out.append(s)
    return out[:cap]


def autocomplete(span: str, settings) -> list[str]:
    if not settings.autocomplete_url:
        return []
    try:
        r = httpx.get(f"{settings.autocomplete_url}/autocompleter", params={"q": span}, timeout=1.0, trust_env=False)
        data = r.json()
        return [s for s in data[1] if isinstance(s, str)][:8] if isinstance(data, list) and len(data) > 1 else []
    except (httpx.HTTPError, ValueError):
        return []


def constraints(message: str) -> dict:
    low = message.lower()
    c = {"month": next((n for m, n in MONTHS.items() if m in low), None), "image": any(w in low for w in IMAGE_WORDS)}
    year = re.search(r"\b(20\d\d)\b", message)
    c["year"] = int(year.group(1)) if year else None
    return c


def pick(slot: str, need: str, candidates: list[str], state: State, d) -> str | None:
    candidates = [c for i, c in enumerate(candidates) if c and c not in candidates[:i]][:24]
    if not candidates:
        return None
    q, th = Q.ladder_questions(slot, need, candidates)
    view = state.view()
    view["candidates"] = {f"cand__{i}": c for i, c in enumerate(candidates)}
    a = d.pneuma.decide(view, q, th, state.round, what="pick")
    if a is None:
        return None
    fits = [(v.confidence, k) for k, v in a.items() if v.choice == "FITS" and v.passed]
    if not fits:
        return None
    return candidates[int(max(fits)[1][len("cand__"):])]


def _need(state: State) -> str:
    return "; ".join(getattr(state, "need", None) or []) or state.message


def fill(slot: str, slot_type: str, state: State, d, proposed: str | None):
    value, source = _fill(slot, slot_type, state, d, proposed)
    state.filled_by[slot] = source   # provenance: learn compares a literal only against a value that was not proposed
    return value


def _fill(slot: str, slot_type: str, state: State, d, proposed: str | None):
    if slot_type == "folder":
        return "files", "default"
    if slot_type == "file":
        return _file(slot, state, d)
    if slot_type == "query" and not any(r.kind == "tool" and r.name == "digest" for r in state.results) and not proposed:
        return state.message, "words"
    need = _need(state)
    cands = [proposed] if proposed else []
    named = state.subject_named is not False   # §4.4: when the message names no subject, rungs 2 and 3 are skipped
    if named:
        cands += [state.message] if slot_type == "query" else spans(state) + state.message.split()[:6]
    if slot_type == "query" and named:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for comps in pool.map(lambda s: autocomplete(s, d.settings), spans(state)):
                cands += comps
    chosen = pick(slot, need, cands, state, d)
    if chosen:
        return chosen, ("plan" if chosen == proposed else "candidates")
    proposals = d.psyche.propose(slot, slot_type, need, state)
    chosen = pick(slot, need, proposals, state, d) if proposals else None
    if chosen:
        return chosen, "proposed"
    if slot_type == "name" and proposals:
        return proposals[0], "proposed"   # a name is internal and reversible; asking the user which title they meant is not worth a turn
    return {"question": f"Which `{slot}` did you mean for: {need}?", "options": (proposals or cands)[:3]}, "ask"


def _file(slot: str, state: State, d):
    atts = state.attachments
    if len(atts) == 1:
        return atts[0].path, "attachment"
    if len(atts) > 1:
        chosen = pick(slot, state.message, [a.name for a in atts], state, d)
        return (next(a.path for a in atts if a.name == chosen), "attachment") if chosen else ({"question": f"Which file for `{slot}`?", "options": [a.name for a in atts][:3]}, "ask")
    c = constraints(state.message)
    files = [f for f in d.vault.files()
             if (c["month"] is None or f.meta["month"] == c["month"]) and (c["year"] is None or f.meta["year"] == c["year"]) and (not c["image"] or f.meta["image"])]
    chosen = pick(slot, state.message, [f.title for f in files], state, d)
    if chosen:
        return f"files/{chosen}", "resolver"
    return {"question": f"Which file for `{slot}`?", "options": [f.title for f in files][:3]}, "ask"
