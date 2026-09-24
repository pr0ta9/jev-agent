import pytest

from soma.tools import CATALOG, run
from soma.vault import Vault


def test_catalog_declares_slot_types_the_design_names():
    assert CATALOG["digest"]["slots"] == {"query": "query"}
    assert CATALOG["write_note"]["slots"] == {"title": "name", "content": "prose"}
    assert all(c["snippet"] for c in CATALOG.values())


def test_read_list_and_write_note_go_through_the_vault(root, settings):
    v = Vault(root / "vault")
    (root / "vault/files/a.txt").write_text("hello", encoding="utf-8")
    assert run("read_file", {"path": "files/a.txt"}, settings, v).output["text"] == "hello"
    assert run("list_files", {"folder": "files"}, settings, v).output["names"] == ["a.txt"]
    r = run("write_note", {"title": "T", "content": "body"}, settings, v)
    assert (root / "vault/memory/t.md").exists() and r.output["path"].endswith("t.md")
    with pytest.raises(PermissionError):
        run("read_file", {"path": "../pyproject.toml"}, settings, v)


def test_digest_result_carries_text_and_aspects_as_points(root, settings, monkeypatch):
    async def fake_digest(query, top=8, **kw):
        return {"digest_evidence": "ETIAS starts in 2026.", "aspects": {"start": "when it starts", "fee": "the fee"}, "run_id": "r1"}

    monkeypatch.setattr("soma.tools.run_digest", fake_digest)
    r = run("digest", {"query": "etias"}, settings, Vault(root / "vault"))
    assert r.output["text"] == "ETIAS starts in 2026." and r.points == ["when it starts", "the fee"]


def test_digest_result_carries_each_aspect_representative_as_a_fact_to_verify(root, settings, monkeypatch):
    rep = {"text": "ETIAS starts in the last quarter of 2026.", "site": "europa.eu", "url": "https://europa.eu/etias", "id": "d0p1"}
    other = {"text": "Unrelated.", "site": "x.com", "url": "https://x.com", "id": "d1p0"}
    blocks = {"T1": {"aspect": "when it starts", "representatives": [rep], "adds": [other]},
              "other": {"aspect": "Other relevant material", "representatives": [other], "adds": []}}

    async def fake_digest(query, top=8, **kw):
        return {"digest_evidence": "...", "aspects": {"T1": "when it starts"}, "blocks": blocks, "run_id": "r1"}

    monkeypatch.setattr("soma.tools.run_digest", fake_digest)
    r = run("digest", {"query": "etias"}, settings, Vault(root / "vault"))
    assert r.output["facts"] == [{"aspect": "when it starts", "site": "europa.eu", "text": "ETIAS starts in the last quarter of 2026."}]
