"""
FolderNode: scans directories for Git/Rsync projects or subfolders.
Uses class-level caches to avoid redundant discovery.
"""

from functools import cached_property
from pathlib import Path
from typing import Dict, Set

from echogit.discovery import (
    ProjectRef,
    discover_local_projects,
    discover_remote_projects,
)
from echogit.node import Node
from echogit.sync.git_sync import GitProjectNode
from echogit.sync.rsync_sync import RsyncProjectNode


class FolderNode(Node):
    """
    A container node that scans its directory for:
      - Git or Rsync project roots → ProjectNode
      - Ordinary sub-folders       → FolderNode
    """

    # cache remote listings (per peer) and local listing (once)
    _remote_cache: Dict[str, Set[ProjectRef]] = {}
    _local_cache: Set[ProjectRef] = set()
    node_by_relpath: Dict[Path, Node] = {}

    def __init__(self, path: Path, **kwargs):
        super().__init__(path, **kwargs)

    @cached_property
    def is_folder(self) -> bool:
        # override Node.is_folder if you want to treat
        # bare-repo dirs (.git, .rsync) as non-folders here
        return True

    def get_icon(self) -> str:
        return "📁" if self.collapse else "📂"

    @cached_property
    def git_path(self) -> Path:
        """FolderNode does not implement git_path."""
        raise NotImplementedError("FolderNode has no git_path")

    def scan(self) -> None:
        self.children.clear()

        # Critical Fix: Initialize root node by relative path
        FolderNode.node_by_relpath[self.relative_path] = self

        # At root only, build local cache once
        if self.parent is None and not FolderNode._local_cache:
            FolderNode._local_cache = set(discover_local_projects(self.path))

        # Immediate local scan
        for child in sorted(self.path.iterdir()):
            if not child.is_dir() or child.name in {".git", ".rsync", ".echogit"}:
                continue

            if (child / ".git").is_dir() or child.suffix == ".git":
                node = GitProjectNode(path=child, parent=self)
            elif (child / ".rsync").is_dir() or child.suffix == ".rsync":
                node = RsyncProjectNode(path=child, parent=self)
            else:
                node = FolderNode(path=child, parent=self)

            node.exists_locally = True
            self.add_child(node)
            node.scan()
            FolderNode.node_by_relpath[node.relative_path] = node

        # Discover missing projects from caches
        if self.parent is None:
            self._add_missing_projects_from_cache(self.relative_path)

    def _add_missing_projects_from_cache(self, data_root: Path) -> None:
        all_refs: Set[ProjectRef] = set(FolderNode._local_cache)

        # Fetch remote project refs, caching per peer
        for peer in self.config.peers:
            if peer not in FolderNode._remote_cache:
                FolderNode._remote_cache[peer] = set(discover_remote_projects(peer))
            all_refs.update(FolderNode._remote_cache[peer])

        for ref in all_refs:

            if ref.rel in FolderNode.node_by_relpath:
                continue  # Already exists locally

            # process only suboflders of data_root
            if not ref.rel.is_relative_to(data_root):
                continue

            # Recursively ensure parent folders exist
            self._ensure_parents(ref.rel.parent, data_root)

            parent_node = FolderNode.node_by_relpath[ref.rel.parent]
            abs_path = (self.config.projects_path / ref.rel).resolve()

            if ref.type == "git":
                node = GitProjectNode(path=abs_path, parent=parent_node)
            elif ref.type == "rsync":
                node = RsyncProjectNode(path=abs_path, parent=parent_node)
            else:
                continue  # Skip unknown type

            node.exists_locally = abs_path.is_dir()
            parent_node.add_child(node)
            node.scan()
            FolderNode.node_by_relpath[ref.rel] = node

    def _ensure_parents(self, rel_path: Path, data_root: Path) -> None:
        """
        Recursively create intermediate FolderNode entries for missing parents.
        this is how we can add remote projects available from peer that we can clone.
        """

        if rel_path == Path(".") or rel_path in FolderNode.node_by_relpath:
            return

        self._ensure_parents(rel_path.parent, data_root)

        parent_node = FolderNode.node_by_relpath[rel_path.parent]

        abs_path = (self.config.projects_path / rel_path).resolve()
        abs_path = rel_path.resolve()

        node = FolderNode(path=abs_path, parent=parent_node)
        node.exists_locally = abs_path.is_dir()
        parent_node.add_child(node)
        FolderNode.node_by_relpath[rel_path] = node
