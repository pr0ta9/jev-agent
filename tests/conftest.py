import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for d in ("vault/memory", "vault/files", "vault/ops", "vault/habits", "traces", "prompts"):
        (tmp_path / d).mkdir(parents=True)
    src = Path(__file__).resolve().parents[1] / "prompts"
    if src.exists():
        for p in src.glob("*.md"):
            (tmp_path / "prompts" / p.name).write_text(p.read_text(encoding="utf-8"), encoding="utf-8")
    return tmp_path


@pytest.fixture
def settings(root: Path):
    from soma.settings import Settings, THRESHOLDS
    return Settings(root=root, typesafe_key="test", typesafe_url="http://jev.test", jev_model="jev-1.13.0",
                    autocomplete_url="", psyche_model="luna", nous_model="astra",
                    thresholds=dict(THRESHOLDS))


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def jev_response(questions: dict, picks: dict[str, tuple[str, float]], model: str = "jev-1.13.0") -> dict:
    """Build a well-formed Jev response: `picks` maps question id to (choice, probability of that choice)."""
    answers = {}
    for key, q in questions.items():
        choice, p = picks[key]
        others = [k for k in q["criteria"] if k != choice]
        rest = (1 - p) / len(others) if others else 0.0
        probs = {k: (p if k == choice else rest) for k in q["criteria"]}
        answers[key] = {"type": "choice", "choice": choice, "probabilities": probs}
    return {"model": model, "answers": answers, "usage": {"input_tokens": 1, "output_tokens": 0}}


class FakePost:
    """Answers every Jev request with the picks given per call, in order. Unlisted ids get NO/DROP at 0.9."""

    def __init__(self, *calls: dict[str, tuple[str, float]]):
        self.calls, self.payloads = list(calls), []

    def __call__(self, payload: dict) -> dict:
        self.payloads.append(payload)
        picks = self.calls.pop(0) if self.calls else {}
        full = {}
        for key, q in payload["questions"].items():
            if key in picks:
                full[key] = picks[key]
            else:
                default = "NO" if "NO" in q["criteria"] else ("DROP" if "DROP" in q["criteria"] else next(iter(q["criteria"])))
                full[key] = (default, 0.9)
        return jev_response(payload["questions"], full, payload["model"])


class FakeCodex:
    """Returns canned texts in order; records prompts and models."""

    def __init__(self, *texts: str, blind: bool = True, writes: dict | None = None):
        self.texts, self.calls, self.blind, self.writes = list(texts), [], blind, writes or {}

    def __call__(self, model, effort, prompt, settings, timeout_s=180, workdir=None):
        from soma.codex import CodexResult
        self.calls.append({"model": model, "effort": effort, "prompt": prompt, "workdir": workdir})
        for name, body in (self.writes.items() if workdir else ()):   # a dispatched agent writes into its work folder
            (workdir / name).write_text(body, encoding="utf-8")
        text = self.texts.pop(0) if self.texts else ""
        return CodexResult(text=text, events=[], usage={}, seconds=0.0, blind=self.blind)
