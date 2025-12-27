"""
parse a local or remote folder and find all available projects.
Skips any subtree that contains a '.echogitskip' marker file.
"""

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Iterator, Set
import shlex

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
        # Determine which pattern we matched (use name/suffix to avoid re-matching)
        if p.name == ".git" or p.suffix == ".git":
            sync_type = "git"
        elif p.name == ".rsync" or p.suffix == ".rsync":
            sync_type = "rsync"
        else:
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
        if p.name == ".git" or p.suffix == ".git":
            sync_type = "git"
        elif p.name == ".rsync" or p.suffix == ".rsync":
            sync_type = "rsync"
        else:
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

    def _ssh_find(path: Path) -> Iterator[ProjectRef]:
        cmd = _build_find_cmd(path)
        success, out = run_ssh_command(peer, cmd)
        if not success:
            return
        yield from _parse_find_output(out, path)

    roots: list[Path] = []
    if getattr(rconfig, "git_path", None):
        roots.append(rconfig.git_path)

    for rt in roots:
        if rt:
            yield from _ssh_find(rt)
