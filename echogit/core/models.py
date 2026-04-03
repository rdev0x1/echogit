from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProjectItem:
    rel: Path
    type: str

    def to_dict(self) -> dict[str, str]:
        return {"rel": str(self.rel), "type": self.type}


@dataclass(frozen=True)
class SyncProgress:
    rel: Path
    type: str
    ok: bool
    dirty: bool
    sync_state: str
    exists_locally: bool

    def to_dict(self) -> dict[str, str | bool]:
        return {
            "rel": str(self.rel),
            "type": self.type,
            "ok": self.ok,
            "dirty": self.dirty,
            "sync_state": self.sync_state,
            "exists_locally": self.exists_locally,
        }


@dataclass(frozen=True)
class SyncResult:
    ok: bool
    root: Path

    def to_dict(self) -> dict[str, str | bool]:
        return {"ok": self.ok, "root": str(self.root)}
