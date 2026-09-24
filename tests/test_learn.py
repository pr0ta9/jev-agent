import json

from conftest import FakeCodex
from soma import learn
from soma.trace import new_trace
from soma.vault import Vault

DRAFT = {"id": "etias-note", "status": "draft", "trigger": ["find the current ETIAS start date and save it as a note"],
         "steps": [{"tool": "digest", "slots": {"query": {"span": "current ETIAS start date"}}},
                   {"tool": "write_note", "slots": {"title": {"literal": "ETIAS start date"}, "content": {"prose": {"tier": ["psyche", "high"], "sources": [0]}}}}]}


def trace_of(root, message, calls, prose, filled=None):
    t = new_trace(root / "traces")
    t.write("message", text=message, files=[])
    for i, (name, slots) in enumerate(calls):
        if name == "write_note":
            t.write("prose", tier=prose["tier"], points=[], sources=prose["sources"], chars=10, round=i + 1)
        t.write("tool", name=name, slots=slots, filled=filled or {}, output="o", points=[], round=i + 1)
    t.write("reply", exit="reply", text="done", rounds=3)
    return t.path


def test_resolve_binding_covers_all_four_kinds():
    msg, results = "find the current ETIAS start date and save it as a note", [{"output": {"text": "digest text"}}]
    assert learn.resolve_binding({"literal": "x"}, msg, results) == "x"
    assert learn.resolve_binding({"span": "current ETIAS start date"}, msg, results) == "current ETIAS start date"
    assert learn.resolve_binding({"step": 0}, msg, results) == "digest text"
    assert learn.resolve_binding({"prose": {"tier": ["psyche", "high"], "sources": [0]}}, msg, results) == {"tier": ("psyche", "high"), "sources": ["digest text"]}


def test_accept_drafts_a_habit_from_a_trace_via_codex(settings, root):
    v = Vault(root / "vault")
    path = trace_of(root, DRAFT["trigger"][0], [("digest", {"query": "current ETIAS start date"}), ("write_note", {"title": "ETIAS start date", "content": "It starts in 2026."})], {"tier": ["psyche", "high"], "sources": [0]})
    out = learn.accept(path, settings, codex=FakeCodex(json.dumps(DRAFT)))
    assert out["drafted"] == "etias-note" and [h["id"] for h in v.habits("draft")] == ["etias-note"]


def test_accept_promotes_a_draft_that_reproduces_the_next_run_and_retires_one_that_does_not(settings, root):
    v = Vault(root / "vault")
    v.save_habit(DRAFT)
    path = trace_of(root, DRAFT["trigger"][0], [("digest", {"query": "current ETIAS start date"}), ("write_note", {"title": "ETIAS start date", "content": "x"})], {"tier": ["psyche", "high"], "sources": [0]})
    out = learn.accept(path, settings, codex=FakeCodex())
    assert out["promoted"] == "etias-note" and v.habits("promoted")[0]["id"] == "etias-note"
    generated = dict(DRAFT, id="gen", status="draft", steps=[DRAFT["steps"][0], {"tool": "write_note", "slots": {"title": {"literal": "A Different Generated Title"}, "content": DRAFT["steps"][1]["slots"]["content"]}}])
    v.save_habit(generated)
    path2 = trace_of(root, DRAFT["trigger"][0], [("digest", {"query": "current ETIAS start date"}), ("write_note", {"title": "ETIAS start date", "content": "x"})], {"tier": ["psyche", "low"], "sources": [0]}, filled={"title": "proposed"})
    assert learn.accept(path2, settings, codex=FakeCodex())["promoted"] == "gen", "a literal accepts a proposed title, and the tier is not compared"
    v.save_habit(dict(DRAFT, id="planned", status="draft"))
    path3 = trace_of(root, DRAFT["trigger"][0], [("digest", {"query": "current official ETIAS start date"}), ("write_note", {"title": "ETIAS Start Date", "content": "x"})], {"tier": ["nous", "medium"], "sources": [0]}, filled={"query": "plan", "title": "plan"})
    assert learn.accept(path3, settings, codex=FakeCodex())["promoted"] == "planned", "values a nous plan proposed are generator output too; the habit's own bindings replay"
    v.save_habit(dict(DRAFT, id="bad", status="draft", steps=DRAFT["steps"][:1]))
    out = learn.accept(path, settings, codex=FakeCodex())
    assert out["retired"] == "bad" and [h["id"] for h in v.habits("retired")] == ["bad"]


def test_a_dispatched_run_is_never_drafted_into_a_habit(root, settings):
    # An agent session is not a replayable sequence of catalog tools; only the harness's own tool steps become habits.
    path = trace_of(root, DRAFT["trigger"][0], [("digest", {"query": "current ETIAS start date"}), ("write_note", {"title": "ETIAS start date", "content": "It starts in 2026."})], {"tier": ["psyche", "high"], "sources": [0]})
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({"t": "0", "kind": "dispatch", "model": "luna", "files": ["etias.md"], "round": 2}) + "\n")
    out = learn.accept(path, settings, codex=FakeCodex(json.dumps(DRAFT)))
    assert out["drafted"] is None and not Vault(root / "vault").habits("draft")
