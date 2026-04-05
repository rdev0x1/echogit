"""
parse a local or remote folder and find all available projects.
Skips any subtree that contains a '.echogitskip' marker file.
"""

from __future__ import annotations

import os
from pathlib import Path
from dataclasses import dataclass
from typing import Iterator, Set
import shlex
import subprocess

from echogit.config import Config
from echogit.utils import run_ssh_command


@dataclass(frozen=True)
class ProjectRef:
    """
    rel   : Path under the peer’s projects_path
    type  : "git" or "rsync"
    """

    rel: Path
    type: str


# marker file to skip a folder subtree
SKIP_MARKER = ".echogitskip"


# match bare‐repo dirs
_PATTERNS = {
    "*.git": "git",
    ".git": "git",
    "*.rsync": "rsync",
    ".rsync": "rsync",
}


REMOTE_DISCOVERY_TIMEOUT = 3


def _normalize(p: Path, sync_type: str) -> ProjectRef:
    """
    Convert a Path match into (relpath, sync_type).
    - Step up if we matched the inner .git/.rsync folder
    - Strip the suffix (bare repo) if present
    """
    # if we matched the metadata dir itself, go up
    repo = p.parent if p.name in (".git", ".rsync") else p

    # strip the suffix from the folder name if it's bare
    if repo.suffix in (".git", ".rsync"):
        repo = repo.with_suffix("")

    # compute relpath under its root
    return ProjectRef(rel=repo, type=sync_type)


def _sync_type_for_path(p: Path) -> str | None:
    if p.name == ".git" or p.suffix == ".git":
        return "git"
    if p.name == ".rsync" or p.suffix == ".rsync":
        return "rsync"
    return None


def is_valid_git_repository_path(path: Path) -> bool:
    """
    Return True when `path` points to a real Git worktree or bare repository.

    A stale or empty `.git` directory should not make a data root syncable as a
    Git project.
    """
    p = Path(path)
    if p.name == ".git":
        return _is_valid_git_worktree(p.parent)
    if p.suffix == ".git":
        return _is_valid_bare_git_repo(p)
    if (p / ".git").exists():
        return _is_valid_git_worktree(p)
    return False


def _is_valid_git_worktree(path: Path) -> bool:
    return _git_check(
        ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
        "true",
    )


def _is_valid_bare_git_repo(path: Path) -> bool:
    return _git_check(
        ["git", "--git-dir", str(path), "rev-parse", "--is-bare-repository"],
        "true",
    )


def _git_check(cmd: list[str], expected: str) -> bool:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0 and result.stdout.strip() == expected


def _build_find_cmd(root: Path) -> str:
    """
    Build a pruning find(1) command:
      - prune any dir that contains SKIP_MARKER
      - print directories matching repo patterns
    """
    tests = " -o ".join(f'-name "{pat}"' for pat in _PATTERNS)
    root_q = shlex.quote(str(root))
    # Check for SKIP_MARKER inside each visited directory; prune if present.
    # Compatible with GNU find, BusyBox, Toybox.
    return (
        f"find {root_q} "
        f"\\( -type d -exec test -e '{{}}/{SKIP_MARKER}' \\; \\) -prune "
        f"-o -type d \\( {tests} \\) -print"
    )


def _parse_find_output(lines: str, root: Path) -> Iterator[ProjectRef]:
    seen: Set[Path] = set()
    for line in lines.splitlines():
        p = Path(line.strip())
        sync_type = _sync_type_for_path(p)
        if sync_type is None:
            continue

        ref = _normalize(p, sync_type)
        rel = ref.rel.relative_to(root)

        # Skip nested projects
        if any(parent in seen for parent in rel.parents):
            continue

        seen.add(rel)
        yield ProjectRef(rel=rel, type=ref.type)


def discover_local_projects(root: Path) -> Iterator[ProjectRef]:
    """
    Yields ProjectRef for every bare‐repo or worktree under 'root'.
    rel is relative to `root`, type is "git" or "rsync".
    """
    root = root.resolve()
    seen: Set[Path] = set()

    def _maybe_ref(p: Path) -> ProjectRef | None:
        sync_type = _sync_type_for_path(p)
        if sync_type is None:
            return None
        if sync_type == "git" and not is_valid_git_repository_path(p):
            return None

        ref = _normalize(p, sync_type)
        rel = ref.rel.relative_to(root)
        if any(parent in seen for parent in rel.parents):
            return None
        seen.add(rel)
        return ProjectRef(rel=rel, type=ref.type)

    for dirpath, dirnames, _ in os.walk(root):
        current = Path(dirpath)
        if (current / SKIP_MARKER).exists():
            dirnames[:] = []
            continue

        # If current directory itself is a repo, yield it and prune.
        ref = _maybe_ref(current)
        if ref is not None:
            yield ref
        if current.name in (".git", ".rsync") or current.suffix in (".git", ".rsync"):
            dirnames[:] = []
            continue

        # If current is a worktree (has .git/.rsync child), yield and prune.
        # Invalid/stale markers are ignored so a bad root marker does not hide
        # valid projects further down the tree.
        if ".git" in dirnames or ".rsync" in dirnames:
            markers = [name for name in (".git", ".rsync") if name in dirnames]
            for marker in markers:
                ref = _maybe_ref(current / marker)
                if ref is not None:
                    yield ref
                    dirnames[:] = []
                    break
            else:
                for marker in markers:
                    dirnames.remove(marker)
                continue
            continue

        # Prune repo dirs and skip-marked dirs; yield repos immediately.
        for name in list(dirnames):
            child = current / name
            if name in (".git", ".rsync") or child.suffix in (".git", ".rsync"):
                ref = _maybe_ref(child)
                if ref is not None:
                    yield ref
                dirnames.remove(name)
                continue
            if (child / SKIP_MARKER).exists():
                dirnames.remove(name)


def discover_remote_projects(peer: str) -> Iterator[ProjectRef]:
    """
    SSH into `peer`, fetch its config.ini for its data_root & bare_root,
    then find the same patterns remotely. Yields ProjectRef(rel, type)
    where rel is relative to each root.
    """
    # grab remote config.ini
    rconfig = Config.get_config_peer(peer)
    if rconfig is None:
        return

    if getattr(rconfig, "git_path", None):
        yield from discover_remote_projects_under(peer, Path("."))


def discover_remote_projects_under(peer: str, subdir: Path) -> Iterator[ProjectRef]:
    """
    SSH into `peer` and find projects under a specific subdir of its root.
    rel is still relative to the peer's root.
    """
    rconfig = Config.get_config_peer(peer)
    if rconfig is None or not getattr(rconfig, "git_path", None):
        return

    root = rconfig.git_path
    base = root / subdir
    cmd = _build_find_cmd(base)
    success, out = run_ssh_command(peer, cmd, timeout=REMOTE_DISCOVERY_TIMEOUT)
    if not success:
        return
    yield from _parse_find_output(out, root)
