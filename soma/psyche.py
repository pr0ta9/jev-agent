"""The voice and the small writer. Renders every exit, fills short slots, proposes candidates. Decides nothing."""
from __future__ import annotations

import json
import re
import time

import httpx

from .codex import CodexResult, run_codex
from .settings import Settings
from .state import State
from .trace import Trace

_MERCURY_EFFORT = {"low": "instant", "medium": "instant", "high": "low"}


def run_mercury(model: str, effort: str, prompt: str, settings: Settings, timeout_s: int = 60) -> CodexResult:
    """The diffusion model as psyche's transport: one chat completion, no tools, so it is blind by construction."""
    started = time.perf_counter()
    text, usage = "", {}
    # Reasoning shares the output budget; at "medium" it consumed all 2,000 tokens twice and left no content.
    for reasoning in (_MERCURY_EFFORT.get(effort, "instant"), "instant"):
        body = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 8000, "reasoning_effort": reasoning}
        resp = httpx.post("https://api.inceptionlabs.ai/v1/chat/completions", json=body, timeout=timeout_s, trust_env=False,
                          headers={"Authorization": f"Bearer {settings.mercury_key}"})
        if resp.status_code != 200:
            usage = {"error": f"http {resp.status_code}: {resp.text[:300]}"}   # fail soft: an empty text is a discarded result, not a crash
            continue
        data = resp.json()
        text = ((data.get("choices") or [{}])[0].get("message", {}).get("content", "") or "").strip()
        usage = data.get("usage", {})
        if text:
            break
    return CodexResult(text=text, usage=usage, seconds=round(time.perf_counter() - started, 2), blind=True)


class Psyche:
    def __init__(self, settings: Settings, codex=run_codex, trace: Trace | None = None):
        self.settings, self.codex, self.trace = settings, codex, trace
        self.psyche_call = run_mercury if settings.psyche_provider == "mercury" else codex

    def _prompt(self, name: str, **fields) -> str:
        text = (self.settings.prompts / f"{name}.md").read_text(encoding="utf-8")
        for key, value in fields.items():
            text = text.replace("{{" + key + "}}", str(value))
        return text

    def _model(self, tier: tuple) -> str:
        if tier[0] == "nous":
            return self.settings.nous_model
        return self.settings.mercury_model if self.settings.psyche_provider == "mercury" else self.settings.psyche_model

    def _run(self, prompt: str, tier: tuple, kind: str) -> str:
        call = self.codex if tier[0] == "nous" else self.psyche_call
        res = call(self._model(tier), tier[1], prompt, self.settings)
        if self.trace:
            self.trace.write("codex", what=kind, tier=list(tier), seconds=res.seconds, usage=res.usage, blind=res.blind)
        return res.text if res.blind else ""

    def render(self, state: State, exit: str, content: str, options: list[str] | None = None) -> str:
        if exit == "end":
            return ""
        turns = "\n".join(f"{t['role']}: {t['text']}" for t in state.turns[-6:]) or "(none)"
        opts = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(options or [])) or "(none)"
        prompt = self._prompt("voice", turns=turns, exit=exit, options=opts, content=content)
        text = self._run(prompt, ("psyche", "low"), "render")
        if len(content) > 600 and len(text) < 0.6 * len(content):
            text = self._run(prompt, ("psyche", "high"), "render") or text   # a fast render dropped facts; measured 2,587 chars cut to a few lines
        return text

    def propose(self, slot: str, slot_type: str, need: str, state: State, tier: tuple = ("psyche", "low")) -> list[str]:
        context = "\n".join(f"- {f.title}: {f.text[:200]}" for f in state.kept_fragments()) or "(none)"
        text = self._run(self._prompt("propose", slot=slot, slot_type=slot_type, need=need, message=state.message, context=context), tier, "propose")
        items = _json_list(text)
        if not re.search(r"\[.*\]", text, re.S) and text.strip() and "\n" not in text.strip():
            items = [text.strip().strip("\"'")]
        return items[:4]

    def expect(self, message: str) -> list[str]:
        return _json_list(self._run(self._prompt("expect", message=message), ("psyche", "low"), "expect"))[:8]

    def write(self, request: str, sources: list[str], points: list[str], tier: tuple) -> str:
        prompt = self._prompt("compose", request=request, points="\n".join(f"- {p}" for p in points) or "- (none)",
                              sources="\n\n".join(f"[{i}] {s}" for i, s in enumerate(sources)) or "(none)")
        return self._run(prompt, tier, "write")


def _json_list(text: str) -> list[str]:
    match = re.search(r"\[.*\]", text, re.S)
    try:
        items = json.loads(match.group(0)) if match else []
    except json.JSONDecodeError:
        items = []
    return [str(x) for x in items if isinstance(x, (str, int, float))] if isinstance(items, list) else []
