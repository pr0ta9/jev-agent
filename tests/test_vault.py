import os
import time
from pathlib import Path

import pytest

from soma.vault import Vault


def make(root: Path) -> Vault:
    (root / "vault/memory/etias.md").write_text("---\ntitle: ETIAS notes\n---\nETIAS is the EU travel authorisation. See [[schengen]].\n", encoding="utf-8")
    (root / "vault/memory/schengen.md").write_text("---\ntitle: Schengen\n---\nThe Schengen area has 29 members.\n", encoding="utf-8")
    (root / "vault/memory/cats.md").write_text("Cats sleep sixteen hours a day.\n", encoding="utf-8")
    (root / "vault/ops/espn.md").write_text("---\ngoal: win the ESPN fantasy league\nstatus: open\n---\n## notes\ntraded for a kicker\n", encoding="utf-8")
    (root / "vault/files/IMG_1204.jpg").write_bytes(b"\xff\xd8")
    dec = time.mktime((2025, 12, 14, 10, 0, 0, 0, 0, -1))
    os.utime(root / "vault/files/IMG_1204.jpg", (dec, dec))
    (root / "vault/files/draft.txt").write_text("a draft about fibre", encoding="utf-8")
    v = Vault(root / "vault")
    v.index()
    return v


def test_fetch_returns_fragments_with_locations_and_follows_one_link(root):
    v = make(root)
    hits = v.fetch("when does ETIAS start")
    ids = [f.id for f in hits]
    assert any(f.location.endswith("etias.md") and "travel authorisation" in f.text for f in hits)
    assert any(f.title == "Schengen" for f in hits), "one hop of [[links]] is expanded"
    assert not any("Cats" in f.text for f in hits)
    assert all(f.kind in {"memory", "file"} for f in hits) and len(ids) == len(set(ids))


def test_files_carry_month_and_extension_for_the_resolver(root):
    v = make(root)
    files = {f.title: f for f in v.files()}
    assert files["IMG_1204.jpg"].meta["ext"] == ".jpg" and files["IMG_1204.jpg"].meta["month"] == 12
    assert "fibre" in files["draft.txt"].text


def test_ops_are_open_first_with_latest_note_and_notes_append(root):
    v = make(root)
    v.write_op("rudeus", "research Future Rudeus")
    v.note_op("rudeus", "found the timeline")
    ops = v.ops()
    assert [o["id"] for o in ops][:2] == ["espn", "rudeus"] and ops[0]["note"] == "traded for a kicker"
    assert ops[1]["note"] == "found the timeline" and ops[1]["status"] == "open"


def test_write_note_stays_under_the_vault_and_refuses_escape(root):
    v = make(root)
    path = v.write_note("ETIAS start date", "It starts in 2026.")
    assert path.parent == root / "vault/memory" and "2026" in path.read_text(encoding="utf-8")
    assert v.write_note("../../evil", "x").parent == root / "vault/memory", "the slug makes escape impossible"
    with pytest.raises(PermissionError):
        v.read_file("../pyproject.toml")


def test_add_file_copies_an_attachment_and_habits_filter_by_status(root, tmp_path):
    v = make(root)
    src = tmp_path / "up.txt"
    src.write_text("uploaded text", encoding="utf-8")
    att = v.add_file(src)
    assert att.kind == "text" and att.text == "uploaded text" and (root / "vault/files/up.txt").exists()
    v.save_habit({"id": "h1", "status": "draft", "trigger": ["x"], "steps": []})
    v.save_habit({"id": "h2", "status": "promoted", "trigger": ["y"], "steps": []})
    assert [h["id"] for h in v.habits("promoted")] == ["h2"] and [h["id"] for h in v.habits("draft")] == ["h1"]


def test_files_a_dispatched_agent_wrote_are_indexed_for_later_requests(root):
    v = Vault(root / "vault")
    (root / "vault/work/trace-1").mkdir(parents=True)
    (root / "vault/work/trace-1/etias.md").write_text("ETIAS has no confirmed start date.", encoding="utf-8")
    v.index()
    assert any(f.location == "work/trace-1/etias.md" for f in v.fetch("ETIAS start date"))
