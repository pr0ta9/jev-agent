"""One JSONL file per request. Recent turns are read back from the newest files."""
from __future__ import annotations

import itertools
import json
import time
import uuid
from pathlib import Path


class Trace:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, kind: str, **data) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **data}, ensure_ascii=False, default=str) + "\n")


_seq = itertools.count()


def new_trace(traces_dir: Path) -> Trace:
    # The Windows clock ticks every ~15 ms; the sequence breaks ties within one process so files sort in creation order.
    return Trace(traces_dir / f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 10**9:09d}-{next(_seq):04d}-{uuid.uuid4().hex[:4]}.jsonl")


def read(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def recent_turns(traces_dir: Path, n: int = 6) -> list[dict]:
    turns: list[dict] = []
    for path in sorted(traces_dir.glob("*.jsonl"), reverse=True):
        pair = []
        for e in read(path):
            if e["kind"] == "message":
                pair.append({"role": "user", "text": e["text"]})
            elif e["kind"] == "reply":
                pair.append({"role": "nyx", "text": e["text"]})
        turns = pair + turns
        if len(turns) >= n:
            break
    return turns[-n:]
