from __future__ import annotations

from functools import cached_property
from pathlib import Path
from typing import Iterator, List

from echogit.config import Config


class Node:
    """
    A hierarchical representation of a filesystem node
    (could be a folder or project).
    """

    def __init__(
        self, path: Path, parent: Node | None = None, config: Config | None = None
    ):
        if (parent is None) == (config is None):
            raise ValueError("Must pass exactly one of parent or config")

        self.path: Path = path.resolve()
        self.name: str = self.path.name
        self.parent: Node | None = parent
        self.children: List[Node] = []
        self._log_lines: list[str] = []
        self._has_error: bool = False
        self.exists_locally: bool = self.path.exists()

        if config is not None:
            self.config = config
        else:
            # Make pylint happy
            assert parent is not None, "parent must be set if config is None"
            self.config = parent.config

    @cached_property
    def is_folder(self) -> bool:
        return False

    def get_icon(self) -> str:
        return "❓"

    def add_child(self, child: Node) -> None:
        child.parent = self
        self.children.append(child)

    def scan(self) -> None:
        """
        Default scan method. Folder-type nodes override this.
        """
        self.children.clear()

    def get_logs(self) -> str:
        return "\n".join(self._log_lines)

    def log(self, msg: str, error: bool = False) -> None:
        """Append a non‐error log line."""
        level = "ERROR" if error else "INFO"
        self._log_lines.append(f"{level}: {msg}")
        if error:
            self._has_error = True

    def has_error(self) -> bool:
        if self._has_error:
            return True
        return any(child.has_error() for child in self.children)

    def sync(self) -> bool:
        success = True
        for child in self.children:
            if not child.sync():
                success = False
        return success

    def clone(self) -> bool:
        return False

    def walk(self) -> Iterator[Node]:
        """
        Yield self and recursively yield all descendants.
        """
        yield self
        for child in self.children:
            yield from child.walk()

    @cached_property
    def relative_path(self) -> Path:
        """
        Returns this node’s path relative to either projects_path or git_path.
        """
        projects_root = self.config.projects_path
        git_root = self.config.git_path

        try:
            return self.path.relative_to(projects_root)
        except Exception:
            pass

        try:
            return self.path.relative_to(git_root)
        except Exception:
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
