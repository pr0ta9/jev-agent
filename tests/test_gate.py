from conftest import FakePost
from soma import gate
from soma.pneuma import Pneuma
from soma.state import State
from soma.vault import Vault


class D:
    def __init__(self, settings, root, post):
        self.settings, self.vault, self.pneuma, self.trace = settings, Vault(root / "vault"), Pneuma(settings, post=post), None


def test_rudeus_research_does_not_attach_to_the_fantasy_league(settings, root):
    (root / "vault/ops/espn.md").write_text("---\ngoal: win the ESPN fantasy league\nstatus: open\n---\n## notes\ntraded\n", encoding="utf-8")
    d = D(settings, root, FakePost({"op__espn": ("YES", 0.6), "outlives": ("NO", 0.9)}))
    s = State(message="research Future Rudeus in Mushoku Tensei")
    gate.gate(s, d)
    assert s.operation is None, "a 0.6 YES is below the 0.85 attach threshold"


def test_a_confident_continuation_attaches_to_the_open_operation(settings, root):
    (root / "vault/ops/espn.md").write_text("---\ngoal: win the ESPN fantasy league\nstatus: open\n---\n## notes\ntraded\n", encoding="utf-8")
    d = D(settings, root, FakePost({"op__espn": ("YES", 0.93)}))
    s = State(message="who should I start at kicker this week")
    gate.gate(s, d)
    assert s.operation["id"] == "espn" and s.operation["goal"].startswith("win")


def test_work_that_outlives_the_exchange_opens_a_new_operation(settings, root):
    d = D(settings, root, FakePost({"outlives": ("YES", 0.9)}))
    s = State(message="plan my move to Lisbon over the next two months")
    gate.gate(s, d)
    assert s.operation and s.operation["status"] == "open" and (root / "vault/ops").glob("*.md")
    assert d.vault.ops()[0]["goal"] == s.message
