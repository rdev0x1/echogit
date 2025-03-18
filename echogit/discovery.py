from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


@dataclass(frozen=True)
class ProjectRef:
    """
    rel   : Path under the peer's projects_path
    type  : always "git" for now
    """

    rel: Path
    type: str


# match bare‐repo dirs
_PATTERNS = {
    "*.git": "git",
    ".git": "git",
}


def _normalize(p: Path, sync_type: str) -> ProjectRef:
    """
    Convert a Path match into (relpath, sync_type).
    - Step up if we matched the inner .git folder
    - Strip the suffix (bare repo) if present
    """
    # if we matched the metadata dir itself, go up
    repo = p.parent if p.name is ".git" else p

    # strip the suffix from the folder name if it's bare
    if repo.suffix is ".git":
        repo = repo.with_suffix("")

    # compute relpath under its root
    return ProjectRef(rel=repo, type=sync_type)


def discover_local_projects(root: Path) -> Iterator[ProjectRef]:
    """
    Yields ProjectRef for every bare‐repo or worktree under 'root'.
    rel is relative to 'root', type is only "git" for now.
    """
    for pat, sync_type in _PATTERNS.items():
        for match in root.rglob(pat):
            ref = _normalize(match, sync_type)
            yield ProjectRef(rel=ref.rel.relative_to(root), type=ref.type)
