"""One Codex session, no user config, JSONL events parsed by code: blind (empty scratch directory, read-only, no web)
for writers, or a dispatched agent confined to its work folder."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from .settings import Settings

_TOOL_ITEMS = ("command_execution", "mcp_tool_call", "web_search", "file_change", "patch")


@dataclass
class CodexResult:
    text: str
    events: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    seconds: float = 0.0
    blind: bool = True


def parse_events(stdout: str) -> tuple[str, dict, bool]:
    text, usage, blind = "", {}, True
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text", "")
        if e.get("type") == "turn.completed" and isinstance(e.get("usage"), dict):
            usage = e["usage"]
        if item.get("type") and any(k in item["type"] for k in _TOOL_ITEMS):
            blind = False
    return text, usage, blind


def run_codex(model: str, effort: str, prompt: str, settings: Settings, timeout_s: int = 180, workdir: Path | None = None) -> CodexResult:
    """Blind by default. With a workdir it is a dispatched agent: its own web search, writes only inside workdir, no timeout."""
    exe = shutil.which("codex") or "codex"
    started = time.perf_counter()
    with tempfile.TemporaryDirectory() as scratch:
        cmd = [exe, "exec", "--json", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
               "--sandbox", "workspace-write" if workdir else "read-only", "-C", str(workdir or scratch),
               "-m", model, "-c", f'model_reasoning_effort="{effort}"']
        if not workdir:
            cmd += ["-c", 'web_search="disabled"']
        elif sys.platform == "win32":
            cmd += ["-c", 'windows.sandbox="elevated"']   # the setting from the user's config; without it Windows blocks every command
        proc = subprocess.run(cmd + ["-"], input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=None if workdir else timeout_s)
    text, usage, blind = parse_events(proc.stdout or "")
    if proc.returncode and not text:
        usage = dict(usage, error=(proc.stderr or "").strip()[-300:] or f"exit {proc.returncode}")
    return CodexResult(text=text.strip(), events=[], usage=usage, seconds=round(time.perf_counter() - started, 2), blind=blind)
