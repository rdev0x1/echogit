"""
parse a local or remote folder and find all available projects.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Set

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


def discover_local_projects(root: Path) -> Iterator[ProjectRef]:
    """
    Yields ProjectRef for every bare‐repo or worktree under 'root'.
    rel is relative to `root`, type is "git" or "rsync".
    """
    seen: Set[Path] = set()
    for pat, sync_type in _PATTERNS.items():
        for match in root.rglob(pat):
            ref = _normalize(match, sync_type)
            rel = ref.rel.relative_to(root)

            # Skip nested projects
            if any(parent in seen for parent in rel.parents):
                continue

            seen.add(rel)
            yield ProjectRef(rel=rel, type=ref.type)


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
    data_root = rconfig.projects_path
    bare_root = rconfig.git_path

    def _ssh_find(path: Path) -> Iterator[ProjectRef]:
        tests = " -o ".join(f'-name "{pat}"' for pat in _PATTERNS)
        cmd = f"find {path} -type d \\( {tests} \\)"
        success, out = run_ssh_command(peer, cmd)
        if not success:
            return

        seen: Set[Path] = set()

        for line in out.splitlines():
            p = Path(line.strip())
            # determine which pattern we matched by checking suffix or folder name
            for pat, sync_type in _PATTERNS.items():
                if p.match(pat):
                    ref = _normalize(p, sync_type)
                    rel = ref.rel.relative_to(path)

                    # Skip nested projects
                    if any(parent in seen for parent in rel.parents):
                        break

                    seen.add(rel)
                    yield ProjectRef(rel=rel, type=ref.type)
                    break

    yield from _ssh_find(data_root)
    if bare_root:
        yield from _ssh_find(bare_root)
