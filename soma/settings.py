"""Settings from environment variables. A .env in the project root is honoured; the shell wins."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

THRESHOLDS = {"fetch": 0.5, "habit": 0.7, "tool": 0.7, "prose": 0.7, "subject": 0.7, "ladder": 0.7,
              "attach": 0.85, "outlives": 0.85, "stop": 0.85}


def _load_dotenv(root: Path) -> None:
    env = root / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"'))


@dataclass(frozen=True)
class Settings:
    root: Path
    typesafe_key: str
    typesafe_url: str
    jev_model: str
    autocomplete_url: str
    psyche_model: str
    nous_model: str
    psyche_provider: str = "codex"     # "codex" | "mercury"
    mercury_key: str = ""
    mercury_model: str = "mercury-2.5"
    nous_scope: str = "all"            # "all": the §7 fill table as written | "planning": nous never writes, psyche writes everything
    dispatch_model: str = "gpt-5.6-luna"   # the dispatched agent; output leaving the vault goes to nous_model
    expect: bool = False               # check replies against an expert's checklist of what a complete answer settles
    max_rounds: int = 6
    decision_timeout_s: float = 1.2
    thresholds: dict = field(default_factory=lambda: dict(THRESHOLDS))

    @property
    def vault(self) -> Path:
        return self.root / "vault"

    @property
    def traces(self) -> Path:
        return self.root / "traces"

    @property
    def prompts(self) -> Path:
        return self.root / "prompts"


def load(root: str | Path | None = None) -> Settings:
    root = Path(root or os.environ.get("SOMA_ROOT") or Path.cwd()).resolve()
    _load_dotenv(root)
    env = os.environ.get
    return Settings(root=root, typesafe_key=env("TYPESAFE_API_KEY", "").strip(),
                    typesafe_url=env("TYPESAFE_API_URL", "https://api.typesafe.ai/v1/systemone"),
                    jev_model=env("JEV_MODEL", "jev-1.13.0"),
                    autocomplete_url=env("AUTOCOMPLETE_URL", "http://localhost:8090"),
                    psyche_model=env("PSYCHE_MODEL", "gpt-5.6-luna"), nous_model=env("NOUS_MODEL", "gpt-6-astra"),
                    psyche_provider=env("PSYCHE_PROVIDER", "codex"), mercury_key=env("MERCURY_API_KEY", "").strip(),
                    mercury_model=env("MERCURY_MODEL", "mercury-2.5"), nous_scope=env("NOUS_SCOPE", "all"),
                    dispatch_model=env("DISPATCH_MODEL", "gpt-5.6-luna"), expect=env("EXPECT_CHECK", "0") in ("1", "true", "yes"))
