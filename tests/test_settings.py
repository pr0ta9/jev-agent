from soma.settings import load


def test_dotenv_in_root_is_honoured_without_overriding_the_shell(root, monkeypatch):
    (root / ".env").write_text('TYPESAFE_API_KEY="from-dotenv"\nPSYCHE_MODEL=luna-x\n', encoding="utf-8")
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    monkeypatch.setenv("PSYCHE_MODEL", "from-shell")
    s = load(root)
    assert s.typesafe_key == "from-dotenv"
    assert s.psyche_model == "from-shell"
    assert s.vault == root / "vault" and s.traces == root / "traces"
