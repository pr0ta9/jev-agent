import dataclasses

from conftest import FakeCodex, FakePost
from soma import loop
from soma.trace import read


def deps_for(settings, post, codex, monkeypatch, digest_text="ETIAS starts in 2026. The fee is 20 euros."):
    async def fake_digest(query, top=8, **kw):
        return {"digest_evidence": digest_text, "aspects": {"start": "when it starts", "fee": "the fee"}, "run_id": "r1"}

    monkeypatch.setattr("soma.tools.run_digest", fake_digest)
    return loop.Deps(settings=settings, pneuma_post=post, codex=codex)


def rounds(events):
    """§3: a round is one triage decide. Gate and ladder picks are decides too, but not rounds."""
    return sum(1 for e in events if e["kind"] == "decide" and e.get("what") == "triage")


def test_fetch_facts_takes_three_rounds_digest_prose_done(settings, monkeypatch):
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.92), "prose": ("NO", 0.9), "satisfied": ("NO", 0.9), "subject": ("NAMED", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.8), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"satisfied": ("YES", 0.95), "point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9)},
    )
    codex = FakeCodex("It starts in 2026 and costs 20 euros.", "Fine. It starts in 2026 and costs 20 euros.")
    out = loop.run("when does ETIAS start and what does it cost", [], deps_for(settings, post, codex, monkeypatch))
    assert out["exit"] == "reply" and out["reply"].startswith("Fine.")
    events = read(out["trace"])
    kinds = [e["kind"] for e in events]
    assert rounds(events) == 3 and "tool" in kinds and "prose" in kinds and kinds[-1] == "reply"
    assert codex.calls[0]["model"] == "luna" and codex.calls[0]["effort"] == "high"
    assert post.payloads[0]["questions"]["outlives"], "the gate asks first"
    assert post.payloads[2]["questions"]["tool__digest"] and "results" in post.payloads[2]["state"]


def test_prose_written_without_sources_is_followed_by_a_fetch_round(settings, monkeypatch):
    post = FakePost(
        {},
        {"prose": ("NEEDED", 0.9), "need": ("STATE", 0.9), "reach": ("WORDS", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"satisfied": ("NO", 0.9), "point__0": ("ABSENT", 0.9), "tool__digest": ("RUN", 0.9), "prose": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"satisfied": ("YES", 0.95), "point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9)},
    )
    codex = FakeCodex("no idea", "It starts in 2026.", "It starts in 2026.")
    out = loop.run("ETIAS start", [], deps_for(settings, post, codex, monkeypatch))
    events = read(out["trace"])
    kinds = [e["kind"] for e in events]
    assert rounds(events) == 4 and kinds.count("prose") == 2 and out["exit"] == "reply"


def test_an_agent_that_fails_ends_in_an_ask_with_a_retry(settings, monkeypatch):
    post = FakePost({}, {"satisfied": ("NO", 0.9)})
    codex = FakeCodex("", "The agent could not finish that. Try again?\n1. try again")
    out = loop.run("do the thing", [], deps_for(settings, post, codex, monkeypatch))
    assert out["exit"] == "ask" and "try again" in codex.calls[-1]["prompt"]


def test_withheld_tools_dispatch_the_agent_and_the_harness_detects_its_files(settings, monkeypatch):
    # No tool is on offer, so nothing is confident: Jev's no-move sends the request to a full agent, which writes its work
    # only into the request's own folder under vault/work/, where the harness finds it.
    post = FakePost({}, {"satisfied": ("NO", 0.9), "prose": ("NO", 0.9)}, {"satisfied": ("YES", 0.95)})
    codex = FakeCodex("ETIAS has no confirmed start date; saved in etias.md.", "Fine. No date yet, and it is saved.",
                      writes={"etias.md": "No confirmed ETIAS start date."})
    out = loop.run("find the current ETIAS start date and save it as a note", [], deps_for(settings, post, codex, monkeypatch), withhold_tools=True)
    events = read(out["trace"])
    dispatched = next(e for e in events if e["kind"] == "dispatch")
    assert dispatched["files"] == ["etias.md"] and (settings.vault / "work" / out["trace"].stem / "etias.md").exists()
    assert out["exit"] == "reply" and "plan" not in [e["kind"] for e in events]


def test_an_aspect_still_missing_after_writing_is_dispatched_with_the_draft(settings, monkeypatch):
    # The writer had nothing more to give and no higher writer is allowed when nous is not a writer; a full agent is.
    settings = dataclasses.replace(settings, nous_scope="planning")
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PARTIAL", 0.9), "point__1": ("PRESENT", 0.9), "research": ("YES", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "satisfied": ("YES", 0.95)},
    )
    codex = FakeCodex("It starts in 2026.", "It starts in 2026 and costs 20 euros.", "Fine. 2026, and 20 euros.")
    out = loop.run("when does ETIAS start and what does it cost", [], deps_for(settings, post, codex, monkeypatch))
    agent = codex.calls[1]
    assert agent["workdir"] is not None and "It starts in 2026." in agent["prompt"] and "the fee" in agent["prompt"]
    assert "Not covered" not in codex.calls[-1]["prompt"] and "20 euros" in codex.calls[-1]["prompt"]


def test_recent_turns_are_judged_like_fragments_and_dropped_unless_kept(settings, monkeypatch):
    from soma.trace import new_trace
    old = new_trace(settings.traces)
    old.write("message", text="save a note about fibre")
    old.write("reply", text="Tch. Noted.")
    post = FakePost({}, {"frag__turn/0": ("DROP", 0.9), "frag__turn/1": ("KEEP", 0.9), "prose": ("NEEDED", 0.9), "need": ("STATE", 0.9), "reach": ("WORDS", 0.9), "exposure": ("VISIBLE", 0.9)},
                    {"satisfied": ("YES", 0.95)})
    codex = FakeCodex("hi", "Hi.")
    out = loop.run("hello", [], deps_for(settings, post, codex, monkeypatch))
    triage = post.payloads[1]
    assert "frag__turn/0" in triage["questions"] and triage["state"]["turns"] == [], "turns are offered as fragments, not shown raw"
    assert "Tch. Noted." in codex.calls[-1]["prompt"] and "save a note about fibre" not in codex.calls[-1]["prompt"], "only the kept turn reaches the voice"
    assert out["exit"] == "reply"


def test_a_promoted_habit_replays_with_no_plan_and_no_extra_rounds(settings, monkeypatch):
    from soma.vault import Vault
    Vault(settings.vault).save_habit({"id": "etias-note", "status": "promoted", "trigger": ["find the current ETIAS start date and save it as a note"],
        "steps": [{"tool": "digest", "slots": {"query": {"span": "current ETIAS start date"}}},
                  {"tool": "write_note", "slots": {"title": {"literal": "ETIAS start date"}, "content": {"prose": {"tier": ["psyche", "high"], "sources": [0]}}}}]})
    post = FakePost({}, {"habit__etias-note": ("FITS", 0.9), "satisfied": ("NO", 0.9)}, {"satisfied": ("YES", 0.95)})
    codex = FakeCodex("It starts in 2026.", "Done. It starts in 2026.")
    out = loop.run("find the current ETIAS start date and save it as a note", [], deps_for(settings, post, codex, monkeypatch))
    events = read(out["trace"])
    kinds = [e["kind"] for e in events]
    assert "habit" in kinds and "plan" not in kinds and rounds(events) == 1 and out["exit"] == "reply", "a replayed habit is the whole request"


def test_an_attachment_fills_the_file_slot_and_a_summary_is_written(settings, monkeypatch, tmp_path):
    src = tmp_path / "notes.txt"
    src.write_text("Fibre keeps you regular.", encoding="utf-8")
    post = FakePost(
        {},
        {"tool__read_file": ("RUN", 0.9), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"satisfied": ("YES", 0.95), "point__0": ("PRESENT", 0.9)},
    )
    codex = FakeCodex("It says fibre keeps you regular.", "Fibre. Regular. Done.")
    out = loop.run("summarise this file", [src], deps_for(settings, post, codex, monkeypatch))
    events = read(out["trace"])
    tool = next(e for e in events if e["kind"] == "tool")
    assert tool["name"] == "read_file" and tool["slots"] == {"path": "files/notes.txt"}
    assert (settings.vault / "files/notes.txt").exists() and out["exit"] == "reply"


def test_a_tool_pneuma_passes_still_runs_when_the_prose_cannot_be_rewritten_again(settings, monkeypatch):
    # 2026-09-23, "Mercury writes all", etias-note-1: the reply stayed PARTIAL after its one rewrite, the loop footnoted
    # it and ended the request, and write_note, passed at 0.95 in that same round, never ran. Since dispatch, the reply
    # that cannot be improved further is the agent's; it is footnoted and the note still gets written.
    partial = {"point__0": ("PARTIAL", 0.9), "point__1": ("PRESENT", 0.9), "tool__write_note": ("RUN", 0.95), "research": ("YES", 0.9), "satisfied": ("NO", 0.9)}
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("WORDS", 0.9), "exposure": ("INTERNAL", 0.9), "satisfied": ("NO", 0.9)},
        partial, partial, partial,
        {"cand__0": ("FITS", 0.9)},
    )
    codex = FakeCodex("No start date is set.", "No start date is set yet.", "The agent found no confirmed start date either.",
                      '["ETIAS start date"]', "No ETIAS start date is set yet.", "Noted. No date yet.")
    out = loop.run("find the current ETIAS start date and save it as a note", [], deps_for(settings, post, codex, monkeypatch))
    events = read(out["trace"])
    assert [e["name"] for e in events if e["kind"] == "tool"] == ["digest", "write_note"]
    assert list((settings.vault / "memory").glob("*.md")), "the note is on disk"


def test_a_reply_that_drops_an_evidence_passage_is_rewritten_once_at_the_same_tier_with_it(settings, monkeypatch):
    # Psyche high is the top tier when nous only plans, so an aspect miss could not be rewritten; a dropped passage can.
    settings = dataclasses.replace(settings, nous_scope="planning")
    deps = deps_for(settings, FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "fact__0": ("MISSING", 0.9), "fact__1": ("STATED", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "fact__0": ("STATED", 0.9), "fact__1": ("STATED", 0.9), "satisfied": ("YES", 0.95)},
    ), codex := FakeCodex("It starts in 2026 and costs 20 euros.", "It starts in 2026 and costs 20 euros; under 18s pay nothing.", "Fine. Under 18s pay nothing."), monkeypatch)
    facts = [{"text": "The fee is 20 euros; applicants under 18 pay nothing.", "site": "europa.eu", "url": "u", "id": "d0p1"},
             {"text": "ETIAS starts in 2026.", "site": "europa.eu", "url": "u", "id": "d0p2"}]

    async def fake_digest(query, top=8, **kw):
        return {"digest_evidence": "ETIAS starts in 2026. The fee is 20 euros; applicants under 18 pay nothing.",
                "aspects": {"fee": "the fee", "start": "when it starts"}, "run_id": "r1",
                "blocks": {"fee": {"aspect": "the fee", "representatives": [facts[0]]}, "start": {"aspect": "when it starts", "representatives": [facts[1]]}}}

    monkeypatch.setattr("soma.tools.run_digest", fake_digest)
    out = loop.run("what does ETIAS cost and when does it start", [], deps)
    prose = [e for e in read(out["trace"]) if e["kind"] == "prose"]
    assert [tuple(e["tier"]) for e in prose] == [("psyche", "high"), ("psyche", "high")]
    assert "applicants under 18 pay nothing" in codex.calls[1]["prompt"], "the rewrite is told which passage it dropped"
    assert "Not covered" not in out["reply"]


def test_a_dropped_passage_is_rewritten_even_when_an_aspect_also_stays_partial(settings, monkeypatch):
    # 2026-09-24, Mercury writes all, ETIAS: "when it becomes mandatory" PARTIAL could not escalate, so the MISSING
    # passage beside it was never rewritten either; the aspect gets its footnote only after the one rewrite.
    settings = dataclasses.replace(settings, nous_scope="planning")
    partial = {"point__0": ("PRESENT", 0.9), "point__1": ("PARTIAL", 0.9), "fact__1": ("STATED", 0.9), "research": ("YES", 0.9), "satisfied": ("NO", 0.9)}
    deps = deps_for(settings, FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        dict(partial, fact__0=("MISSING", 0.9)),
        dict(partial, fact__0=("STATED", 0.9)),
    ), codex := FakeCodex("It costs 20 euros; no date is set.", "It costs 20 euros, under 18s pay nothing; no date is set.", "Fine."), monkeypatch)

    async def fake_digest(query, top=8, **kw):
        return {"digest_evidence": "The fee is 20 euros; applicants under 18 pay nothing. No start date is set.",
                "aspects": {"fee": "the fee", "start": "when it starts"}, "run_id": "r1",
                "blocks": {"fee": {"aspect": "the fee", "representatives": [{"text": "The fee is 20 euros; applicants under 18 pay nothing.", "site": "europa.eu"}]},
                           "start": {"aspect": "when it starts", "representatives": [{"text": "No start date is set.", "site": "europa.eu"}]}}}

    monkeypatch.setattr("soma.tools.run_digest", fake_digest)
    loop.run("what does ETIAS cost and when does it start", [], deps)
    assert "applicants under 18 pay nothing" in codex.calls[1]["prompt"], "the rewrite carries the dropped passage"
    assert codex.calls[2]["workdir"] is not None and "when it starts" in codex.calls[2]["prompt"], "the partial aspect then goes to a full agent"


def test_an_empty_rewrite_never_replaces_the_draft(settings, monkeypatch):
    # 2026-09-24, Mercury + Astra, python313: the nous high rewrite came back empty and the reply said the sources
    # covered nothing, though the 1,604-character first draft had passed two of three points.
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PARTIAL", 0.9), "satisfied": ("NO", 0.9)},
    )
    codex = FakeCodex("It starts in 2026 and costs 20 euros.", "", "Fine. It starts in 2026 and costs 20 euros.")
    loop.run("when does ETIAS start and what does it cost", [], deps_for(settings, post, codex, monkeypatch))
    assert "It starts in 2026 and costs 20 euros." in codex.calls[-1]["prompt"], "the voice renders the draft"


def test_a_failed_web_search_is_said_plainly_with_a_retry_not_answered_from_nothing(settings, monkeypatch):
    # 2026-09-24, Rudeus: SearXNG's engines were rate-limited, the digest returned no results twice, and the loop wrote
    # five source-less drafts until the reply claimed nobody knows anything about the topic.
    post = FakePost({}, {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)})
    codex = FakeCodex("The web search came back empty. Want me to try again?")
    deps = deps_for(settings, post, codex, monkeypatch)

    async def failing_digest(query, top=8, **kw):
        return {"error": "no search results", "run_id": "r1"}

    monkeypatch.setattr("soma.tools.run_digest", failing_digest)
    out = loop.run("what happened to Future Rudeus in Mushoku Tensei", [], deps)
    events = read(out["trace"])
    assert out["exit"] == "ask" and not [e for e in events if e["kind"] == "prose"]
    assert "search" in codex.calls[-1]["prompt"].lower() and "try again" in codex.calls[-1]["prompt"]


def test_a_write_after_a_dropped_repeat_search_respects_the_nous_scope(settings, monkeypatch):
    settings = dataclasses.replace(settings, nous_scope="planning")
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"tool__digest": ("RUN", 0.95), "subject": ("NAMED", 0.9), "reach": ("SEVERAL", 0.9), "exposure": ("EXTERNAL", 0.9), "satisfied": ("NO", 0.9)},
        {"cand__0": ("FITS", 0.95)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "satisfied": ("YES", 0.95)},
    )
    codex = FakeCodex("It starts in 2026 and costs 20 euros.", "Fine. 2026, 20 euros.")
    loop.run("when does ETIAS start and what does it cost", [], deps_for(settings, post, codex, monkeypatch))
    assert codex.calls[0]["model"] != settings.nous_model, "nous only plans under the planning scope"


def test_a_gap_jev_judges_unresearchable_is_footnoted_without_dispatching(settings, monkeypatch):
    settings = dataclasses.replace(settings, nous_scope="planning")
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PARTIAL", 0.9), "point__1": ("PRESENT", 0.9), "research": ("NO", 0.9), "satisfied": ("NO", 0.9)},
    )
    codex = FakeCodex("It starts in 2026.", "Fine. 2026.")
    loop.run("when does ETIAS start and what does it cost", [], deps_for(settings, post, codex, monkeypatch))
    assert all(c["workdir"] is None for c in codex.calls), "no agent for a gap more research cannot fill"
    assert "Not covered by the sources: the fee" in codex.calls[-1]["prompt"]


def _expect_deps(settings, post, codex, monkeypatch):
    return deps_for(dataclasses.replace(settings, nous_scope="planning", expect=True), post, codex, monkeypatch)


def test_an_unmet_expectation_the_digest_never_covered_goes_to_the_agent(settings, monkeypatch):
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "expect__0": ("ANSWERED", 0.9), "expect__1": ("MISSING", 0.9),
         "research": ("YES", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "expect__0": ("ANSWERED", 0.9), "expect__1": ("ANSWERED", 0.9), "satisfied": ("YES", 0.95)},
    )
    codex = FakeCodex("It starts in 2026 and costs 20 euros.", '["when does it start?", "is it a visa?"]',
                      "It starts in 2026, costs 20 euros, and is not a visa.", "Fine. Not a visa, either.")
    loop.run("when does ETIAS start and what does it cost", [], _expect_deps(settings, post, codex, monkeypatch))
    agent = codex.calls[2]
    assert agent["workdir"] is not None and "is it a visa?" in agent["prompt"], "the agent is told what the answer still lacks"
    assert "Not covered" not in codex.calls[-1]["prompt"]


def test_an_unmet_expectation_nobody_could_research_is_neither_dispatched_nor_footnoted(settings, monkeypatch):
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("ONE", 0.9), "exposure": ("VISIBLE", 0.9), "satisfied": ("NO", 0.9)},
        {"point__0": ("PRESENT", 0.9), "point__1": ("PRESENT", 0.9), "expect__0": ("MISSING", 0.9), "research": ("NO", 0.9), "satisfied": ("YES", 0.9)},
    )
    codex = FakeCodex("It starts in 2026 and costs 20 euros.", '["who decided the fee?"]', "Fine. 2026, 20 euros.")
    loop.run("when does ETIAS start and what does it cost", [], _expect_deps(settings, post, codex, monkeypatch))
    assert all(c["workdir"] is None for c in codex.calls) and "who decided the fee" not in codex.calls[-1]["prompt"]


def test_the_expert_checklist_is_asked_for_once_per_request(settings, monkeypatch):
    partial = {"point__0": ("PARTIAL", 0.9), "point__1": ("PRESENT", 0.9), "expect__0": ("ANSWERED", 0.9), "satisfied": ("NO", 0.9)}
    post = FakePost(
        {},
        {"tool__digest": ("RUN", 0.95), "satisfied": ("NO", 0.9)},
        {"prose": ("NEEDED", 0.9), "reach": ("WORDS", 0.9), "exposure": ("INTERNAL", 0.9), "satisfied": ("NO", 0.9)},
        partial, dict(partial, point__0=("PRESENT", 0.9), satisfied=("YES", 0.95)),
    )
    codex = FakeCodex("It starts in 2026.", '["when does it start?"]', "It starts in 2026 and costs 20 euros.", "Fine.")
    loop.run("when does ETIAS start and what does it cost", [], _expect_deps(settings, post, codex, monkeypatch))
    assert sum("complete, expert answer" in c["prompt"] for c in codex.calls) == 1
