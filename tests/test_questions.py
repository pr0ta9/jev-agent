from soma.pneuma import Answer
from soma.questions import (ESCALATION, actions_from, conflicted, escalate, fill_table, gate_questions, is_done, ladder_questions, missing_facts, unmet,
                            no_move, triage_questions, verify_pending)
from soma.state import Fragment, State


def ans(choice, conf=0.9, th=0.7):
    return Answer(choice, conf, {}, th)


def test_fill_table_matches_design_section_7():
    assert fill_table("WORDS", "INTERNAL") == ("psyche", "low")
    assert fill_table("ONE", "VISIBLE") == ("psyche", "high")
    assert fill_table("SEVERAL", "VISIBLE") == ("nous", "medium")
    assert fill_table("SEVERAL", "EXTERNAL") == ("nous", "high")
    assert escalate(("psyche", "high")) == ("nous", "medium") and escalate(ESCALATION[-1]) is None


def test_gate_questions_ask_once_per_operation_at_the_attach_threshold(settings):
    view = {"message": "m"}
    q, th = gate_questions(view, [{"id": "espn", "goal": "win the league", "status": "open", "note": "traded"}], settings)
    assert set(q) == {"op__espn", "outlives"}
    assert th["op__espn"] == 0.85 and th["outlives"] == 0.85
    assert view["operations"][0]["id"] == "espn"


def test_triage_questions_cover_habits_tools_prose_and_stop(settings):
    s = State(message="find the ETIAS start date", fragments=[Fragment("f1", "memory", "t", "x", "l")])
    q, th = triage_questions(s.view(), [{"id": "h1", "trigger": ["a"]}], ["digest", "write_note"], pending=None, fragments=s.fragments, settings=settings)
    for key in ("habit__h1", "tool__digest", "tool__write_note", "prose", "reach", "exposure", "subject", "satisfied", "frag__f1"):
        assert key in q
    assert th["frag__f1"] == 0.5 and th["satisfied"] == 0.85 and th["tool__digest"] == 0.7


def test_no_move_and_actions_prefer_habits_then_tools_then_prose():
    a = {"habit__h1": ans("FITS"), "tool__digest": ans("RUN"), "prose": ans("NEEDED"), "need": ans("STATE"), "reach": ans("WORDS"), "exposure": ans("VISIBLE")}
    acts = actions_from(a, State(message="m"))
    assert [x.kind for x in acts] == ["habit"] and acts[0].name == "h1"
    a["habit__h1"] = ans("NO")
    acts = actions_from(a, State(message="m"))
    assert [(x.kind, x.name) for x in acts] == [("tool", "digest")]
    a["tool__digest"] = ans("RUN", conf=0.5)
    acts = actions_from(a, State(message="m"))
    assert [x.kind for x in acts] == ["prose"] and acts[0].tier == ("psyche", "low")
    a["prose"] = ans("NO")
    assert no_move(a, points_covered=False)


def test_triage_view_carries_tool_snippets(settings):
    view = State(message="m").view()
    triage_questions(view, [], [{"name": "digest", "snippet": "Search the web."}], pending=None, fragments=[], settings=settings)
    assert view["tools"] == [{"name": "digest", "snippet": "Search the web."}]


def test_prose_with_several_sources_is_not_runnable_until_points_are_covered():
    a = {"prose": ans("NEEDED"), "reach": ans("SEVERAL"), "exposure": ans("VISIBLE")}
    assert no_move(a, points_covered=False)
    assert not no_move(a, points_covered=True)


def test_is_done_needs_satisfied_and_every_point_present():
    a = {"satisfied": ans("YES", 0.9, 0.85), "point__0": ans("PRESENT"), "point__1": ans("ABSENT")}
    assert not is_done(a)
    a["point__1"] = ans("PRESENT")
    assert is_done(a)


def test_verify_pending_routes_absent_points_to_fetch_or_rewrite():
    a = {"point__0": ans("ABSENT"), "point__1": ans("PARTIAL")}
    assert verify_pending(a, ["start date", "fee"], covered={"fee"}) == {"fetch": ["start date"], "rewrite": ["fee"]}


def test_ladder_questions_are_one_yes_no_per_candidate():
    q, th = ladder_questions("query", "the start date", ["etias start date", "etias fee"])
    assert set(q) == {"cand__0", "cand__1"} and all(th[k] == 0.7 for k in q)
    assert set(q["cand__0"]["criteria"]) == {"FITS", "NO"} and "etias start date" in q["cand__0"]["instructions"]


def test_need_web_adds_the_digest_when_no_tool_answer_passed():
    a = {"need": ans("WEB"), "tool__digest": ans("RUN", conf=0.6), "prose": ans("NO")}
    acts = actions_from(a, State(message="m"), available=("digest", "read_file"))
    assert [(x.kind, x.name) for x in acts] == [("tool", "digest")]
    assert actions_from(a, State(message="m")) == [], "only tools the loop offers can be added"


def test_a_tool_that_writes_prose_waits_for_a_source():
    a = {"tool__write_note": ans("RUN"), "tool__digest": ans("RUN")}
    acts = actions_from(a, State(message="m"), points_covered=False, needs_sources=("write_note",))
    assert [x.name for x in acts] == ["digest"]
    acts = actions_from(a, State(message="m"), points_covered=True, needs_sources=("write_note",))
    assert sorted(x.name for x in acts) == ["digest", "write_note"]


def test_a_file_tool_needs_an_attachment_or_a_confident_vault_answer():
    from soma.state import Attachment
    a = {"tool__read_file": ans("RUN"), "need": ans("WEB")}
    assert actions_from(a, State(message="fiber intake?"), needs_file=("read_file",)) == []
    a["need"] = ans("VAULT")
    assert [x.name for x in actions_from(a, State(message="m"), needs_file=("read_file",))] == ["read_file"]
    a["need"] = ans("WEB")
    s = State(message="summarise this", attachments=[Attachment("a.txt", "files/a.txt", "text")])
    assert [x.name for x in actions_from(a, s, needs_file=("read_file",))] == ["read_file"]


def test_a_verified_prose_ends_the_request_without_a_confident_satisfied():
    a = {"satisfied": ans("NO", 0.9, 0.85)}
    assert is_done(a, verified=True) and not is_done(a)


EVIDENCE = """Evidence for: when does ETIAS start and what does it cost

Topics: T1: when it starts; T2: the fee

## ETIAS FAQ
https://example.eu/etias
[d0p1; T1] ETIAS starts in the last quarter of 2026.
[d0p4; T2; possible disagreement] The fee is 7 euros.
"""


def test_a_point_is_conflicted_only_when_a_passage_under_its_topic_is_marked_as_disagreeing():
    assert conflicted(EVIDENCE, "the fee")
    assert not conflicted(EVIDENCE, "when it starts")
    assert not conflicted(EVIDENCE, "who needs it"), "a point the digest never named has nothing to disagree about"


def test_a_verified_prose_does_not_end_the_request_while_pneuma_passes_a_tool_run():
    # A note request whose reply was verified with a "not covered" footnote still has the note to write.
    a = {"satisfied": ans("NO", 0.95), "tool__write_note": ans("RUN", 0.95)}
    assert not is_done(a, verified=True)


FACTS = [{"aspect": "the fee", "site": "europa.eu", "text": "The fee is 20 euros; applicants under 18 pay nothing."},
         {"aspect": "the fee", "site": "etias.com", "text": "It costs EUR 20."},
         {"aspect": "when it starts", "site": "europa.eu", "text": "ETIAS starts in the last quarter of 2026."}]


def test_a_pending_reply_is_checked_against_every_evidence_passage_not_only_every_aspect(settings):
    # Aspect points pass a reply that drops a sub-fact ("what happened to Roxy" without the rat); a passage is finer.
    view = {"message": "what does ETIAS cost and when does it start"}
    pending = {"text": "It costs 20 euros and starts in late 2026.", "points": ["the fee", "when it starts"], "facts": FACTS}
    q, _ = triage_questions(view, [], [], pending=pending, fragments=[], settings=settings)
    assert {"fact__0", "fact__1", "fact__2"} <= set(q)
    assert "under 18 pay nothing" in view["facts"][0]


def test_missing_facts_are_the_passages_pneuma_confidently_marks_missing():
    a = {"fact__0": ans("MISSING"), "fact__1": ans("STATED"), "fact__2": ans("MISSING", 0.5)}
    assert missing_facts(a, FACTS) == [FACTS[0]]


def test_a_pending_reply_also_asks_whether_more_research_could_fill_its_gaps(settings):
    # A gap the sources simply do not record (Oldeus's family) cost a 106 s dispatch that found nothing more.
    view = {"message": "m"}
    q, th = triage_questions(view, [], [], pending={"text": "t", "points": ["p"], "facts": []}, fragments=[], settings=settings)
    assert set(q["research"]["criteria"]) == {"YES", "NO"} and th["research"] == settings.thresholds["tool"]


def test_a_pending_reply_is_also_checked_against_what_a_complete_answer_needs(settings):
    # The digest's own aspects cannot show what it never fetched: Jev marked Python's limitations covered in every run
    # while two limitations the rubric expects were absent. An expert's checklist is proposed, then judged.
    view = {"message": "m"}
    pending = {"text": "t", "points": ["p"], "facts": [], "expected": ["which extensions turn the GIL back on?"]}
    q, _ = triage_questions(view, [], [], pending=pending, fragments=[], settings=settings)
    assert set(q["expect__0"]["criteria"]) == {"ANSWERED", "MISSING", "NOT_NEEDED"}
    assert view["expected"] == ["which extensions turn the GIL back on?"]


def test_unmet_expectations_are_the_items_pneuma_confidently_marks_missing():
    items = ["a?", "b?", "c?"]
    a = {"expect__0": ans("MISSING"), "expect__1": ans("NOT_NEEDED"), "expect__2": ans("MISSING", 0.5)}
    assert unmet(a, items) == ["a?"]
