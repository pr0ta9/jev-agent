from pathlib import Path

from soma.codex import parse_events, run_codex

FIX = Path(__file__).parent / "fixtures" / "codex_events.jsonl"


def test_parse_events_extracts_text_usage_and_blindness():
    text, usage, blind = parse_events(FIX.read_text(encoding="utf-8"))
    assert text == '{"ok": true}' and usage["output_tokens"] == 9 and blind


def test_a_command_execution_event_marks_the_result_not_blind():
    lines = FIX.read_text(encoding="utf-8") + '{"type":"item.completed","item":{"type":"command_execution","command":"ls"}}\n'
    assert parse_events(lines)[2] is False


def test_run_codex_builds_a_blind_command_and_pipes_the_prompt(settings, monkeypatch):
    seen = {}

    class Proc:
        stdout, stderr, returncode = FIX.read_text(encoding="utf-8"), "", 0

    def fake_run(cmd, **kw):
        seen["cmd"], seen["input"] = cmd, kw.get("input")
        return Proc()

    monkeypatch.setattr("soma.codex.subprocess.run", fake_run)
    res = run_codex("luna", "low", "say ok", settings)
    cmd = seen["cmd"]
    assert res.text == '{"ok": true}' and res.blind
    for flag in ("--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check"):
        assert flag in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only" and cmd[cmd.index("-m") + 1] == "luna"
    assert 'model_reasoning_effort="low"' in cmd and cmd[-1] == "-" and seen["input"] == "say ok"


def test_a_writer_session_cannot_search_the_web(settings, monkeypatch):
    # Web search is on in codex exec even with user config ignored; Astra at high effort searched during a rewrite on
    # 2026-09-24, and the non-blind result was discarded, leaving an empty reply.
    seen = {}

    class Proc:
        stdout, stderr, returncode = FIX.read_text(encoding="utf-8"), "", 0

    monkeypatch.setattr("soma.codex.subprocess.run", lambda cmd, **kw: seen.setdefault("cmd", cmd) and Proc())
    run_codex("astra", "high", "write", settings)
    assert 'web_search="disabled"' in seen["cmd"]


def test_a_dispatched_agent_searches_and_writes_only_in_its_work_folder_and_is_never_cut_off(settings, monkeypatch, tmp_path):
    seen = {}

    class Proc:
        stdout, stderr, returncode = FIX.read_text(encoding="utf-8"), "", 0

    def fake_run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return Proc()

    monkeypatch.setattr("soma.codex.subprocess.run", fake_run)
    monkeypatch.setattr("soma.codex.sys.platform", "win32")
    run_codex("luna", "medium", "task", settings, workdir=tmp_path)
    cmd = seen["cmd"]
    assert cmd[cmd.index("--sandbox") + 1] == "workspace-write" and cmd[cmd.index("-C") + 1] == str(tmp_path)
    assert 'web_search="disabled"' not in cmd, "a dispatched agent does its own research"
    assert 'windows.sandbox="elevated"' in cmd, "without it, Windows blocks every command and the agent can write nothing"
    assert seen["kw"]["timeout"] is None, "an agent returns a result or an error; agents measured up to 442 s on one question"


def test_a_failed_codex_run_reports_its_error(settings, monkeypatch):
    class Proc:
        stdout, stderr, returncode = "", "error: not logged in", 1

    monkeypatch.setattr("soma.codex.subprocess.run", lambda cmd, **kw: Proc())
    res = run_codex("luna", "low", "x", settings)
    assert res.text == "" and "not logged in" in res.usage["error"]
