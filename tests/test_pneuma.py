import pytest

from conftest import FakePost, fixture, jev_response
from soma.pneuma import Pneuma, PneumaError, choice, validate


def test_choice_rejects_empty_and_oversized_option_sets():
    with pytest.raises(ValueError):
        choice("q", {})
    with pytest.raises(ValueError):
        choice("q", {str(i): "x" for i in range(256)})


def test_validate_rejects_a_choice_that_is_not_the_argmax():
    q = {"q1": choice("q", {"YES": "y", "NO": "n"})}
    bad = jev_response(q, {"q1": ("YES", 0.3)})
    with pytest.raises(ValueError):
        validate(bad, q, "jev-1.13.0")
    validate(fixture("jev_choice.json"), q, "jev-1.13.0")


def test_decide_returns_answers_with_thresholds_applied(settings):
    q = {"q1": choice("q", {"YES": "y", "NO": "n"}), "q2": choice("q", {"YES": "y", "NO": "n"})}
    p = Pneuma(settings, post=FakePost({"q1": ("YES", 0.91), "q2": ("YES", 0.6)}))
    a = p.decide({"message": "m"}, q, {"q1": 0.7, "q2": 0.7})
    assert a["q1"].choice == "YES" and a["q1"].passed
    assert a["q2"].choice == "YES" and not a["q2"].passed and a["q2"].confidence == 0.6


def test_decide_retries_once_then_returns_none(settings):
    calls = []

    def failing(payload):
        calls.append(payload)
        raise PneumaError("timeout")

    p = Pneuma(settings, post=failing)
    assert p.decide({"m": 1}, {"q1": choice("q", {"YES": "y", "NO": "n"})}, {}) is None
    assert len(calls) == 2


def test_decide_sends_bearer_and_model(settings):
    seen = {}

    def post(payload):
        seen.update(payload)
        return jev_response(payload["questions"], {"q1": ("NO", 0.8)}, payload["model"])

    Pneuma(settings, post=post).decide({"m": 1}, {"q1": choice("q", {"YES": "y", "NO": "n"})}, {})
    assert seen["model"] == "jev-1.13.0" and seen["state"] == {"m": 1}
