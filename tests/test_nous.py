from conftest import FakeCodex
from soma import nous
from soma.state import State


def test_dispatch_runs_the_agent_in_its_work_folder_and_returns_its_answer_and_files(settings, tmp_path):
    work = tmp_path / "work" / "trace-1"
    fake = FakeCodex("Build with --disable-gil. Sources: https://docs.python.org", writes={"notes.md": "free-threading notes"})
    tool, prose = nous.dispatch(State(message="how do I enable no-GIL Python"), settings, work, fake)
    assert fake.calls[0]["workdir"] == work and fake.calls[0]["model"] == settings.dispatch_model
    assert tool.kind == "tool" and tool.name == "dispatch" and tool.output["files"] == ["notes.md"], "the harness sees what the agent wrote"
    assert tool.output["text"] == prose.output and prose.kind == "prose" and prose.output.startswith("Build with")


def test_dispatch_after_a_failed_check_carries_the_draft_and_the_missing_points(settings, tmp_path):
    fake = FakeCodex("complete answer")
    _, prose = nous.dispatch(State(message="m"), settings, tmp_path / "w", fake, draft="partial draft", missing=["its limitations"],
                             points=["how to enable it", "its limitations"])
    assert "partial draft" in fake.calls[0]["prompt"] and "its limitations" in fake.calls[0]["prompt"]
    assert prose.points == ["how to enable it", "its limitations"], "the agent's answer is verified on the same points"


def test_output_that_leaves_the_vault_goes_to_the_strong_model(settings, tmp_path):
    fake = FakeCodex("done")
    nous.dispatch(State(message="m"), settings, tmp_path / "w", fake, external=True)
    assert fake.calls[0]["model"] == settings.nous_model


def test_an_agent_that_returns_nothing_ends_in_an_ask_with_a_retry(settings, tmp_path):
    tool, ask = nous.dispatch(State(message="m"), settings, tmp_path / "w", FakeCodex(""))
    assert tool.output["error"] and ask.kind == "ask" and "try again" in ask.output["options"]
