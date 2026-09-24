"""The strong reasoner as a dispatched agent: a full Codex session with its own search, confined to one work folder."""
from __future__ import annotations

from pathlib import Path

from .codex import run_codex
from .settings import Settings
from .state import Result, State


def dispatch(state: State, settings: Settings, workdir: Path, codex=run_codex, trace=None, draft: str = "",
             missing: list[str] = (), points: list[str] = (), external: bool = False) -> list[Result]:
    workdir.mkdir(parents=True, exist_ok=True)
    before = {p for p in workdir.rglob("*") if p.is_file()}
    context = "\n".join(f"- {f.title}: {f.text[:300]}" for f in state.kept_fragments()) or "(none)"
    results = "\n".join(f"- {r.name}: {str(r.output)[:300]}" for r in state.results if r.kind == "tool") or "(none)"
    prompt = ((settings.prompts / "dispatch.md").read_text(encoding="utf-8").replace("{{message}}", state.message)
              .replace("{{context}}", context).replace("{{results}}", results).replace("{{draft}}", draft or "(none)")
              .replace("{{missing}}", "\n".join(f"- {m}" for m in missing) or "(none)"))
    model = settings.nous_model if external else settings.dispatch_model
    res = codex(model, "medium", prompt, settings, workdir=workdir)
    files = sorted(p.relative_to(workdir).as_posix() for p in workdir.rglob("*") if p.is_file() and p not in before)
    error = None if res.text else (res.usage.get("error") or "the agent returned no answer")
    if trace:
        trace.write("dispatch", model=model, seconds=res.seconds, usage=res.usage, files=files, error=error, round=state.round)
    tool = Result("tool", "dispatch", {"workdir": str(workdir)}, {"text": res.text, "files": files, "error": error}, state.round)
    if error:
        ask = {"question": f"The agent could not finish that ({error[:120]}). Try again?", "options": ["try again", "never mind"]}
        return [tool, Result("ask", "dispatch", {}, ask, state.round)]
    return [tool, Result("prose", "dispatch", {}, res.text, state.round, points=list(points), tier=("nous", "agent"))]
