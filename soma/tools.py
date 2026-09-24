"""The tools code can run. Their inputs are slots; the catalog is the only place slot types are known."""
from __future__ import annotations

import asyncio
from pathlib import Path

from jev_digest.pipeline import run_digest

from .settings import Settings
from .state import Result
from .vault import TEXT_EXT, Vault

CATALOG = {
    "digest": {"slots": {"query": "query"}, "snippet": "Search the web and return judged passages grouped by source page, each labelled with the aspect it answers."},
    "read_file": {"slots": {"path": "file"}, "snippet": "Read one file from the vault and return its text."},
    "list_files": {"slots": {"folder": "folder"}, "snippet": "List the files in a vault folder."},
    "write_note": {"slots": {"title": "name", "content": "prose"}, "snippet": "Save a note with a title and written content into the vault's memory."},
}


def run(name: str, slots: dict, settings: Settings, vault: Vault, round_no: int = 0) -> Result:
    if name == "digest":
        out = asyncio.run(run_digest(slots["query"], top=10))   # top=10 is the setting the §9.2 fact counts were measured at
        if out.get("error") == "no search results":   # SearXNG drops a query now and then; the same query usually succeeds at once
            out = asyncio.run(run_digest(slots["query"], top=10))
        text = out.get("digest_evidence", "") if "error" not in out else ""
        aspects = out.get("aspects") or {}
        facts = [{"aspect": b["aspect"], "site": r["site"], "text": r["text"]}
                 for k, b in (out.get("blocks") or {}).items() if k in aspects for r in b.get("representatives", [])]
        return Result("tool", name, slots, {"text": text, "run_id": out.get("run_id"), "error": out.get("error"), "facts": facts}, round_no,
                      points=list(aspects.values()))
    if name == "read_file":
        path = slots["path"]
        text = vault.read_file(path) if Path(path).suffix.lower() in TEXT_EXT else vault.describe(path)
        return Result("tool", name, slots, {"text": text}, round_no)
    if name == "list_files":
        return Result("tool", name, slots, {"names": vault.list_files(slots.get("folder", "files"))}, round_no)
    if name == "write_note":
        path = vault.write_note(slots["title"], slots["content"])
        return Result("tool", name, slots, {"path": str(path), "text": slots["content"]}, round_no)
    raise KeyError(f"unknown tool {name}")
