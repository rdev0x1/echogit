from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import List

from echogit.config import Config


@dataclass
class NodeLogState:
    lines: list[str] = field(default_factory=list)
    has_error: bool = False


@dataclass
class NodeSyncState:
    state: str = "unknown"
    gen: int = 0
    last_gen: int = -1
    current_gen: int | None = None


@dataclass
class NodePresenceState:
    exists_locally: bool = False
    scanned: bool = False
    collapse: bool = True
    is_dirty: bool = False
    remote_peers: list[str] = field(default_factory=list)


@dataclass
class NodeState:
    log: NodeLogState = field(default_factory=NodeLogState)
    sync: NodeSyncState = field(default_factory=NodeSyncState)
    presence: NodePresenceState = field(default_factory=NodePresenceState)


class Node:
    """
    A hierarchical representation of a filesystem node
    (could be a folder or project).
    """

    sync_parallel = True
    SYNC_WORKERS = 4

    def __init__(
        self, path: Path, parent: Node | None = None, config: Config | None = None
    ):
        if (parent is None) == (config is None):
            raise ValueError("Must pass exactly one of parent or config")

        self.path: Path = path.resolve()
        self.name: str = self.path.name
        self.parent: Node | None = parent
        self.children: List[Node] = []
        self.state = NodeState()
        self.state.presence.exists_locally = self.path.exists()

        if config is not None:
            self.config = config
        else:
            # Make pylint happy
            assert parent is not None, "parent must be set if config is None"
            self.config = parent.config

    @cached_property
    def depth(self) -> int:
        """Number of edges between this node and the rootcached."""
        if self.parent is None:
            return 0
        return self.parent.depth + 1

    @cached_property
    def is_folder(self) -> bool:
        """Folder node contains other folders node or projects node"""
        return False

    def get_icon(self) -> str:
        """Used by TUI"""
        return "❓"

    def add_child(self, child: Node) -> None:
        child.parent = self
        self.children.append(child)

    def scan(self, on_update=None) -> None:
        """
        Default scan method. Folder-type nodes override this.
        """
        _ = on_update
        self.children.clear()
        self.state.presence.scanned = True
        self.state.log.has_error = False

    def ensure_scanned_deep(self, on_update=None) -> None:
        """
        Ensure this node and all descendants are scanned without clearing
        existing children unless necessary.
        """
        self.ensure_scanned(on_update=on_update)
        for child in list(self.children):
            child.ensure_scanned_deep(on_update=on_update)

    def ensure_scanned(self, on_update=None) -> None:
        """Optional hook for lazy child discovery."""
        _ = on_update

    def log(self, msg: str, error: bool = False) -> None:
        """Append a non‐error log line."""
        level = "ERROR" if error else "INFO"
        self.state.log.lines.append(f"{level}: {msg}")
        if error:
            self.state.log.has_error = True

    def has_error(self) -> bool:
        """
        Return true if this node had an error when executing a command, or if
        any child had an error.
        """
        if self.state.log.has_error:
            return True
        return any(child.has_error() for child in list(self.children))

    def is_dirty(self) -> bool:
        """
        Return True if this node represents a dirty working tree.
        """
        return self.state.presence.is_dirty

    def is_scanned(self) -> bool:
        """
        Return True if this node's scan has completed.
        """
        return self.state.presence.scanned

    def sync_state(self) -> str:
        """
        Return sync state: unknown, ok, or error.
        """
        return self.state.sync.state

    def begin_sync(self) -> int:
        """
        Start a sync generation and return its id.
        """
        self.state.sync.gen += 1
        self.state.sync.current_gen = self.state.sync.gen
        return self.state.sync.gen

    def mark_synced(self, gen: int, success: bool) -> None:
        """
        Record the result of a sync generation.
        """
        self.state.sync.last_gen = gen
        self.state.sync.state = "ok" if success else "error"

    def sync(self, on_progress=None) -> bool:
        """
        sync a project using git or rsync.
        """
        self.state.log.has_error = False
        success = True
        children = list(self.children)
        if self.sync_parallel and self.SYNC_WORKERS > 1 and len(children) > 1:
            with ThreadPoolExecutor(max_workers=self.SYNC_WORKERS) as executor:
                futures = [
                    executor.submit(child.sync, on_progress=on_progress)
                    for child in children
                ]
                for future in futures:
                    try:
                        if not future.result():
                            success = False
                    except Exception:  # pylint: disable=broad-exception-caught
                        success = False
        else:
            for child in children:
                if not child.sync(on_progress=on_progress):
                    success = False
        return self._finalize_sync(success, on_progress)

    def _finalize_sync(self, success: bool, on_progress=None) -> bool:
        self.state.sync.state = "ok" if success else "error"
        if self.state.sync.current_gen is not None:
            self.mark_synced(self.state.sync.current_gen, success)
        if on_progress:
            on_progress(self, success)
        return success

    def is_synced(self, gen: int) -> bool:
        """
        Return True if this node has a sync result for the given generation.
        """
        return self.state.sync.last_gen == gen

    def skip_sync(self, on_progress=None) -> bool:
        """
        Skip sync without marking ok/error (used for unreachable peers).
        """
        self.state.sync.state = "unknown"
        self.state.sync.current_gen = None
        if on_progress:
            on_progress(self, True)
        return True

    def clone(self) -> bool:
        """
        clone a project using git clone or rsync.
        """
        return False

    @cached_property
    def relative_path(self) -> Path:
        """
        Returns this node’s path relative to either projects_path or git_path.
        """
        projects_root = self.config.projects_path
        git_root = self.config.git_path

        try:
            return self.path.relative_to(projects_root)
        except ValueError:
            pass

        if git_root is not None:
            try:
                return self.path.relative_to(git_root)
            except ValueError:
                pass

        raise ValueError(
            f"Node path {self.path!r} is not under "
            f"{projects_root!r} or {git_root!r}"
        )

    @cached_property
    def git_path(self) -> Path:
        raise NotImplementedError("sync() must be implemented by subclasses")

    def __repr__(self) -> str:
        return f"<Node {self.name}>"
