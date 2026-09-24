import io
import sys

from soma import cli


def test_the_reply_reaches_a_redirected_windows_stdout_as_utf8(monkeypatch, settings):
    # Piped or redirected, Python on Windows encodes stdout as cp1252 and "€" and "’" arrive as mojibake in Git Bash.
    raw = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    monkeypatch.setattr(cli, "load", lambda: settings)
    monkeypatch.setattr(cli.loop, "run", lambda *a, **k: {"reply": "It costs €20 and isn’t a visa.", "exit": "reply", "trace": "t"})
    cli.main(["what is ETIAS"])
    sys.stdout.flush()
    assert raw.getvalue().decode("utf-8").strip() == "It costs €20 and isn’t a visa."
