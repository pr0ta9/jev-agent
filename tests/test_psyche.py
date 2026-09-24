from conftest import FakeCodex
from soma.psyche import Psyche
from soma.state import State


def test_render_fills_the_voice_template_and_returns_codex_text(settings):
    fake = FakeCodex("Fine. It starts in 2026. Not that I looked it up for you.")
    p = Psyche(settings, codex=fake)
    text = p.render(State(message="when?", turns=[{"role": "user", "text": "hi"}]), "reply", "It starts in 2026.")
    assert text.startswith("Fine.")
    prompt = fake.calls[0]["prompt"]
    assert "EXIT: reply" in prompt and "It starts in 2026." in prompt and "user: hi" in prompt
    assert fake.calls[0]["model"] == "luna" and fake.calls[0]["effort"] == "low"


def test_ask_lists_options_and_end_renders_nothing(settings):
    fake = FakeCodex("Pick one.\n1. a\n2. b")
    p = Psyche(settings, codex=fake)
    assert "1. a" in p.render(State(message="m"), "ask", "Which?", options=["a", "b"])
    assert p.render(State(message="m"), "end", "") == "" and len(fake.calls) == 1


def test_propose_parses_a_json_list_and_write_uses_the_tier_model(settings):
    fake = FakeCodex('["etias start date", "etias launch 2026", "when etias begins"]', "composed text")
    p = Psyche(settings, codex=fake)
    assert p.propose("query", "query", "the start date", State(message="m")) == ["etias start date", "etias launch 2026", "when etias begins"]
    assert p.write("summarise", ["src"], ["point"], ("nous", "medium")) == "composed text"
    assert fake.calls[1]["model"] == "astra" and fake.calls[1]["effort"] == "medium"


def test_mercury_serves_the_psyche_tier_and_codex_keeps_nous(settings, monkeypatch):
    import dataclasses
    seen = {}

    class Resp:
        status_code = 200

        def json(self):
            return {"choices": [{"message": {"content": "Hmph. 2026."}}], "usage": {"completion_tokens": 3}}

    def fake_post(url, json, timeout, trust_env, headers):
        seen.update(url=url, body=json, auth=headers["Authorization"])
        return Resp()

    monkeypatch.setattr("soma.psyche.httpx.post", fake_post)
    s = dataclasses.replace(settings, psyche_provider="mercury", mercury_key="mk", mercury_model="mercury-2.5")
    fake = FakeCodex("nous text")
    p = Psyche(s, codex=fake)
    assert p.render(State(message="when?"), "reply", "It starts in 2026.") == "Hmph. 2026."
    assert seen["url"].endswith("/v1/chat/completions") and seen["auth"] == "Bearer mk"
    assert seen["body"]["model"] == "mercury-2.5" and seen["body"]["reasoning_effort"] == "instant"
    assert p.write("x", [], [], ("nous", "medium")) == "nous text" and fake.calls[0]["model"] == "astra"


def test_a_render_that_shrinks_long_content_is_redone_at_higher_effort(settings):
    content = "fact. " * 200
    fake = FakeCodex("too short", "long enough " * 120)
    p = Psyche(settings, codex=fake)
    out = p.render(State(message="m"), "reply", content)
    assert out.startswith("long enough") and [c["effort"] for c in fake.calls] == ["low", "high"]


def test_a_session_that_touched_a_tool_is_discarded(settings):
    p = Psyche(settings, codex=FakeCodex("leaked", blind=False))
    assert p.write("x", [], [], ("psyche", "low")) == ""


def test_a_bare_one_line_proposal_is_one_candidate_not_none(settings):
    # 2026-09-24, Mercury writes all, etias-note-1: a 5-token propose reply parsed to no candidates, so a note title
    # went to the user as "ETIAS / find / the".
    p = Psyche(settings, codex=FakeCodex('"ETIAS Start Date"'))
    assert p.propose("title", "name", "a title for the note", State(message="m")) == ["ETIAS Start Date"]


def test_expect_lists_what_a_complete_answer_must_answer(settings):
    p = Psyche(settings, codex=FakeCodex('["how is it enabled?", "which extensions turn the GIL back on?"]'))
    assert p.expect("How do I enable free-threaded Python 3.13?") == ["how is it enabled?", "which extensions turn the GIL back on?"]
    assert Psyche(settings, codex=FakeCodex("no list here, sorry")).expect("m") == []
