"""Jev client. Choice questions only: the shape the digest validated against the live API."""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from .settings import Settings
from .trace import Trace


class PneumaError(RuntimeError):
    pass


@dataclass
class Answer:
    choice: str
    confidence: float
    probabilities: dict
    threshold: float

    @property
    def passed(self) -> bool:
        return self.confidence >= self.threshold


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    if not 1 <= len(criteria) <= 255:
        raise ValueError(f"Choice needs 1-255 options, got {len(criteria)}")
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def validate(result: Any, questions: dict, model: str) -> None:
    if not isinstance(result, dict) or result.get("model") != model:
        raise ValueError("model missing or differs from the requested model")
    answers = result.get("answers")
    if not isinstance(answers, dict) or set(answers) != set(questions):
        raise ValueError("answers do not match the questions")
    for key, question in questions.items():
        a = answers[key]
        probs = a.get("probabilities") if isinstance(a, dict) else None
        if a.get("type") != "choice" or not isinstance(probs, dict) or set(probs) != set(question["criteria"]):
            raise ValueError(f"malformed answer for {key}")
        if not all(isinstance(p, (int, float)) and math.isfinite(p) and 0 <= p <= 1 for p in probs.values()):
            raise ValueError(f"bad probabilities for {key}")
        chosen = a.get("choice")
        if chosen not in probs or probs[chosen] < max(probs.values()) - 1e-9:
            raise ValueError(f"choice is not the highest-probability option for {key}")


class Pneuma:
    """One request per call, one retry, then None so the caller takes the ask exit."""

    def __init__(self, settings: Settings, post: Callable[[dict], dict] | None = None, trace: Trace | None = None):
        self.settings, self.post, self.trace = settings, post or self._http_post, trace

    def _http_post(self, payload: dict) -> dict:
        s = self.settings
        try:
            resp = httpx.post(s.typesafe_url, json=payload, headers={"Authorization": f"Bearer {s.typesafe_key}"},
                              timeout=s.decision_timeout_s, trust_env=False)
        except httpx.HTTPError as exc:
            raise PneumaError(f"transport: {exc}") from exc
        if resp.status_code != 200:
            raise PneumaError(f"http {resp.status_code}")
        return resp.json()

    def decide(self, view: dict, questions: dict[str, dict], thresholds: dict[str, float], round_no: int = 0, what: str = "triage") -> dict[str, Answer] | None:
        payload = {"model": self.settings.jev_model, "state": view, "questions": questions}
        last: Exception | None = None
        for _ in range(2):
            try:
                result = self.post(payload)
                validate(result, questions, self.settings.jev_model)
            except (PneumaError, ValueError) as exc:
                last = exc
                continue
            answers = {}
            for key in questions:
                a = result["answers"][key]
                answers[key] = Answer(a["choice"], float(a["probabilities"][a["choice"]]), a["probabilities"], thresholds.get(key, 0.7))
            if self.trace:
                self.trace.write("decide", what=what, round=round_no, usage=result.get("usage") or {}, questions=len(questions),
                                 answers={k: {"choice": v.choice, "confidence": round(v.confidence, 3), "passed": v.passed} for k, v in answers.items()})
            return answers
        if self.trace:
            self.trace.write("decide_failed", what=what, round=round_no, error=str(last))
        return None
