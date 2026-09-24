"""Markdown notes plus a rebuildable FTS5 index. Every write is confined to the vault: that is the permission reflex."""
from __future__ import annotations

import re
import shutil
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import yaml

from .state import Attachment, Fragment

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".yaml", ".yml"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic"}
_WORD = re.compile(r"[\w一-鿿]+")


def _frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    head, _, body = text[3:].partition("\n---")
    meta = {k.strip(): v.strip() for k, _, v in (line.partition(":") for line in head.strip().splitlines()) if k.strip()}
    return meta, body.lstrip("\n")


def _slug(title: str) -> str:
    return re.sub(r"[^a-z0-9一-鿿]+", "-", title.lower()).strip("-")[:60] or "note"


class Vault:
    def __init__(self, root: Path):
        self.root = root.resolve()
        for d in ("memory", "files", "ops", "habits"):
            (self.root / d).mkdir(parents=True, exist_ok=True)
        self.db = self.root / ".index.sqlite"

    def _inside(self, path: str | Path) -> Path:
        full = (self.root / path).resolve()
        if not full.is_relative_to(self.root):
            raise PermissionError(f"{path} is outside the vault")
        return full

    def _docs(self):
        for p in (self.root / "memory").glob("*.md"):
            meta, body = _frontmatter(p.read_text(encoding="utf-8"))
            yield f"memory/{p.stem}", "memory", meta.get("title", p.stem), body, str(p.relative_to(self.root)), {}
        for f in self.files():
            yield f.id, "file", f.title, f.text, f.location, f.meta

    def index(self) -> int:
        con = sqlite3.connect(self.db)
        con.execute("drop table if exists docs")
        con.execute("create virtual table docs using fts5(id, kind, title, text, location)")
        rows = [(i, k, t, x, loc) for i, k, t, x, loc, _ in self._docs()]
        con.executemany("insert into docs values (?,?,?,?,?)", rows)
        con.commit()
        con.close()
        return len(rows)

    def fetch(self, query: str, per_kind: int = 8) -> list[Fragment]:
        words = [w for w in _WORD.findall(query.lower()) if len(w) > 2][:12]
        if not words or not self.db.exists():
            return []
        con = sqlite3.connect(self.db)
        match = " OR ".join(f'"{w}"' for w in words)
        rows = con.execute("select id, kind, title, text, location from docs where docs match ? order by bm25(docs) limit 40", (match,)).fetchall()
        con.close()
        out, seen, per = [], set(), {}
        for i, k, t, x, loc in rows:
            if per.get(k, 0) >= per_kind or i in seen:
                continue
            per[k] = per.get(k, 0) + 1
            seen.add(i)
            out.append(Fragment(i, k, t, x, loc))
        for frag in list(out):
            for link in re.findall(r"\[\[([^\]]+)\]\]", frag.text):
                target = self.root / "memory" / f"{_slug(link)}.md"
                if target.exists() and f"memory/{target.stem}" not in seen:
                    meta, body = _frontmatter(target.read_text(encoding="utf-8"))
                    seen.add(f"memory/{target.stem}")
                    out.append(Fragment(f"memory/{target.stem}", "memory", meta.get("title", target.stem), body, f"memory/{target.name}"))
        return out

    def files(self) -> list[Fragment]:
        out, work = [], self.root / "work"
        for p in sorted((self.root / "files").iterdir()) + (sorted(work.rglob("*")) if work.is_dir() else []):   # work/: what dispatched agents wrote
            if not p.is_file():
                continue
            loc = p.relative_to(self.root).as_posix()
            ext, mtime = p.suffix.lower(), datetime.fromtimestamp(p.stat().st_mtime)
            text = p.read_text(encoding="utf-8", errors="replace")[:4000] if ext in TEXT_EXT else ""
            out.append(Fragment(f"file/{p.name}" if loc.startswith("files/") else f"file/{loc}", "file", p.name, text, loc,
                                {"ext": ext, "month": mtime.month, "year": mtime.year, "image": ext in IMAGE_EXT}))
        return out

    def add_file(self, src: Path) -> Attachment:
        dest = self._inside(Path("files") / src.name)
        shutil.copyfile(src, dest)
        ext = dest.suffix.lower()
        kind = "text" if ext in TEXT_EXT else "image" if ext in IMAGE_EXT else "other"
        text = dest.read_text(encoding="utf-8", errors="replace")[:20000] if kind == "text" else ""
        return Attachment(dest.name, f"files/{dest.name}", kind, text)

    def read_file(self, path: str) -> str:
        return self._inside(path).read_text(encoding="utf-8", errors="replace")

    def describe(self, path: str) -> str:
        p = self._inside(path)
        if not p.exists():
            return f"{p.name}: not found"
        when = datetime.fromtimestamp(p.stat().st_mtime)
        return f"{p.name}: {'image' if p.suffix.lower() in IMAGE_EXT else 'binary'} file from {when:%Y-%m}"

    def list_files(self, folder: str = "files") -> list[str]:
        return sorted(p.name for p in self._inside(folder).iterdir() if p.is_file())

    def write_note(self, title: str, content: str) -> Path:
        path = self._inside(Path("memory") / f"{_slug(title)}.md")
        path.write_text(f"---\ntitle: {title}\nwritten: {time.strftime('%Y-%m-%d')}\n---\n{content.strip()}\n", encoding="utf-8")
        return path

    def ops(self) -> list[dict]:
        out = []
        for p in sorted((self.root / "ops").glob("*.md")):
            meta, body = _frontmatter(p.read_text(encoding="utf-8"))
            notes = [ln for ln in body.split("## notes", 1)[-1].splitlines() if ln.strip()] if "## notes" in body else []
            out.append({"id": p.stem, "goal": meta.get("goal", ""), "status": meta.get("status", "open"), "note": notes[-1] if notes else ""})
        return sorted(out, key=lambda o: (o["status"] != "open", o["id"]))

    def write_op(self, op_id: str, goal: str) -> None:
        self._inside(Path("ops") / f"{_slug(op_id)}.md").write_text(f"---\ngoal: {goal}\nstatus: open\n---\n## notes\n", encoding="utf-8")

    def note_op(self, op_id: str, note: str) -> None:
        with self._inside(Path("ops") / f"{_slug(op_id)}.md").open("a", encoding="utf-8") as fh:
            fh.write(note.strip().replace("\n", " ") + "\n")

    def habits(self, status: str = "promoted") -> list[dict]:
        out = []
        for p in sorted((self.root / "habits").glob("*.yaml")):
            h = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            if h.get("status") == status:
                out.append(h)
        return out

    def save_habit(self, habit: dict) -> Path:
        path = self._inside(Path("habits") / f"{_slug(habit['id'])}.yaml")
        path.write_text(yaml.safe_dump(habit, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path
