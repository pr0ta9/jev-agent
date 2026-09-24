from conftest import FakeCodex, FakePost
from soma import ladder
from soma.pneuma import Pneuma
from soma.psyche import Psyche
from soma.state import Attachment, Fragment, Result, State, fold
from soma.vault import Vault


class D:
    def __init__(self, settings, root, post=None, codex=None):
        self.settings, self.vault = settings, Vault(root / "vault")
        self.pneuma, self.psyche, self.trace = Pneuma(settings, post=post or FakePost()), Psyche(settings, codex=codex or FakeCodex()), None


def test_spans_come_from_the_message_and_from_state():
    s = State(message='Compare "ETIAS start date" with Oldeus in December 2025', attachments=[Attachment("IMG_1204.jpg", "files/IMG_1204.jpg", "image")],
              fragments=[Fragment("f1", "memory", "Schengen", "x", "l")], kept=["f1"])
    got = ladder.spans(s)
    for want in ("ETIAS start date", "Oldeus", "December 2025", "IMG_1204.jpg", "Schengen"):
        assert want in got
    assert len(got) <= 8


def test_one_matching_attachment_fills_a_file_slot_without_a_question(settings, root):
    d = D(settings, root)
    s = State(message="summarise this", attachments=[Attachment("a.txt", "files/a.txt", "text")])
    assert ladder.fill("path", "file", s, d, None) == "files/a.txt" and d.pneuma.post.payloads == []


def test_a_reference_is_resolved_from_the_file_index_by_month_and_kind(settings, root):
    import os, time
    (root / "vault/files/IMG_1204.jpg").write_bytes(b"x")
    dec = time.mktime((2025, 12, 14, 10, 0, 0, 0, 0, -1))
    os.utime(root / "vault/files/IMG_1204.jpg", (dec, dec))
    (root / "vault/files/report.txt").write_text("r", encoding="utf-8")
    d = D(settings, root, post=FakePost({"cand__0": ("FITS", 0.9)}))
    s = State(message="which file is that picture from December?")
    assert ladder.fill("path", "file", s, d, None) == "files/IMG_1204.jpg"
    assert d.pneuma.post.payloads[0]["state"]["candidates"] == {"cand__0": "IMG_1204.jpg"}, "the text report is filtered out by month and kind"


def test_first_query_is_the_users_own_words_and_the_gap_round_walks_autocomplete(settings, root, monkeypatch):
    monkeypatch.setattr(ladder, "autocomplete", lambda span, settings: ["etias start date", "etias fee"] if "ETIAS" in span else [])
    d = D(settings, root, post=FakePost({"cand__1": ("FITS", 0.9), "cand__0": ("FITS", 0.75)}))
    s = State(message="ETIAS facts")
    assert ladder.fill("query", "query", s, d, None) == "ETIAS facts"
    fold(s, [Result("tool", "digest", {"query": "ETIAS facts"}, {"text": "t"}, 1, points=["the fee"])])
    s.need = ["the start date"]
    assert ladder.fill("query", "query", s, d, None) == "etias start date"


def test_a_name_slot_takes_the_top_proposal_instead_of_asking(settings, root):
    d = D(settings, root, post=FakePost({}, {}), codex=FakeCodex('["ETIAS start date", "ETIAS note"]'))
    s = State(message="save a note about the ETIAS start date")
    assert ladder.fill("title", "name", s, d, None) == "ETIAS start date" and s.filled_by["title"] == "proposed"


def test_when_nothing_fits_the_ladder_asks_with_the_top_candidates(settings, root, monkeypatch):
    monkeypatch.setattr(ladder, "autocomplete", lambda span, settings: [])
    d = D(settings, root, post=FakePost({}, {}), codex=FakeCodex('["a", "b", "c"]'))
    s = State(message="thing")
    fold(s, [Result("tool", "digest", {"query": "thing"}, {"text": "t"}, 1)])
    s.need = ["the fee"]
    out = ladder.fill("query", "query", s, d, None)
    assert isinstance(out, dict) and out["options"][:3] == ["a", "b", "c"]
