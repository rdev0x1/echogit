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
    discover_remote_projects_under,
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
    _remote_cache: Dict[tuple[str, Path], Set[ProjectRef]] = {}
    _local_cache: Set[ProjectRef] = set()
    node_by_relpath: Dict[Path, Node] = {}

    # marker file to skip a folder subtree
    SKIP_MARKER = ".echogitskip"

    def __init__(self, path: Path, **kwargs):
        super().__init__(path, **kwargs)
        self._remote_loaded = False

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

    def scan(self, on_update=None) -> None:
        self.children.clear()

        # Skip whole subtree if marker file present
        if (self.path / self.SKIP_MARKER).exists():
            self.log(f"scan skipped: {self.SKIP_MARKER} present")
            self._scanned = True
            return

        if self.parent is None and on_update:
            on_update(status="Scanning folders...", increment=False, force=True)

        # Index this folder only if it’s inside an allowed root
        rel_self = self._rel_from_roots(self.path)
        if rel_self is None:
            self.log("scan skipped: outside configured roots")
            self._scanned = True
            return
        FolderNode.node_by_relpath[rel_self] = self

        # Immediate local scan
        for child in sorted(self.path.iterdir()):
            if not child.is_dir() or child.name in {".git", ".rsync", ".echogit"}:
                continue

            # Resolve symlinks once, but prevent escaping our roots
            target = child.resolve()
            child_rel = self._rel_from_roots(target)
            if child_rel is None:
                continue

            # Skip child subtree if marker file present
            if (target / self.SKIP_MARKER).exists():
                continue

            # Prevent cycles and duplicate traversal
            # same logical directory already indexed
            if child_rel in FolderNode.node_by_relpath:
                continue
            # symlink points to this folder or any ancestor -> cycle
            if self._is_ancestor_path(target):
                continue

            if (target / ".git").is_dir() or target.suffix == ".git":
                node = GitProjectNode(path=target, parent=self)
            elif (target / ".rsync").is_dir() or target.suffix == ".rsync":
                node = RsyncProjectNode(path=target, parent=self)
            else:
                node = FolderNode(path=target, parent=self)

            node.exists_locally = True
            self.add_child(node)
            if on_update:
                on_update(node=node)
            node.scan(on_update=on_update)
            FolderNode.node_by_relpath[child_rel] = node

        # Discover missing projects from caches
        if self.parent is None:
            self._add_local_projects_from_cache(rel_self, on_update=on_update)

        self.log(f"scan done: {len(self.children)} child node(s)")
        self._scanned = True

    def ensure_scanned(self, on_update=None) -> None:
        if not self._remote_loaded:
            self._load_remote_projects_for_node(on_update=on_update)

    def _add_local_projects_from_cache(
        self, data_root: Path, on_update=None
    ) -> None:
        if not FolderNode._local_cache:
            if on_update:
                on_update(status="Indexing cache...", increment=False, force=True)
            for ref in discover_local_projects(self.path):
                FolderNode._local_cache.add(ref)
                self._add_project_from_cache(
                    ref, data_root, on_update=on_update
                )
            if on_update:
                on_update(status="Scanning folders...", increment=False, force=True)

    def _rel_from_roots(self, p: Path) -> Path | None:
        """
        Return p relative to projects_path or git_path; None if it escapes both.
        """
        pr = p.resolve()
        try:
            return pr.relative_to(self.config.projects_path)
        except ValueError:
            if self.config.git_path:
                try:
                    return pr.relative_to(self.config.git_path)
                except ValueError:
                    pass
        return None

    def _is_ancestor_path(self, p: Path) -> bool:
        """Return True if resolved path p is this node or any ancestor."""
        rp = p.resolve()
        cur = self
        while cur is not None:
            if cur.path.resolve() == rp:
                return True
            cur = cur.parent
        return False

    def _ensure_parents(
        self, rel_path: Path, data_root: Path, on_update=None
    ) -> bool:
        """
        Recursively create intermediate FolderNode entries for missing parents.
        this is how we can add remote projects available from peer that we can clone.
        """

        if rel_path == Path(".") or rel_path in FolderNode.node_by_relpath:
            return True

        ret = self._ensure_parents(rel_path.parent, data_root, on_update=on_update)
        if ret is False:
            return False

        parent_node = FolderNode.node_by_relpath[rel_path.parent]

        # Only create childs node under folder node. We dont want childs under
        # projects node.
        if not parent_node.is_folder:
            return False

        abs_path = (self.config.projects_path / rel_path).resolve()

        node = FolderNode(path=abs_path, parent=parent_node)
        node.exists_locally = abs_path.is_dir()
        node._scanned = True
        parent_node.add_child(node)
        FolderNode.node_by_relpath[rel_path] = node
        if on_update:
            on_update(node=node, increment=False)
        return True

    def _add_project_from_cache(
        self, ref: ProjectRef, data_root: Path, on_update=None
    ) -> None:
        if ref.rel in FolderNode.node_by_relpath:
            return  # Already exists locally

        # process only subfolders of data_root
        if not ref.rel.is_relative_to(data_root):
            return

        # Recursively ensure parent folders exist
        ret = self._ensure_parents(ref.rel.parent, data_root, on_update=on_update)
        if ret is False:
            return

        parent_node = FolderNode.node_by_relpath[ref.rel.parent]
        abs_path = (self.config.projects_path / ref.rel).resolve()

        if ref.type == "git":
            node = GitProjectNode(path=abs_path, parent=parent_node)
        elif ref.type == "rsync":
            node = RsyncProjectNode(path=abs_path, parent=parent_node)
        else:
            return  # Skip unknown type

        node.exists_locally = abs_path.is_dir()
        parent_node.add_child(node)
        parent_node._scanned = True
        if on_update:
            on_update(node=node)
        node.scan(on_update=on_update)
        FolderNode.node_by_relpath[ref.rel] = node

    def _load_remote_projects_for_node(self, on_update=None) -> None:
        data_root = self._rel_from_roots(self.path)
        if data_root is None:
            self._remote_loaded = True
            return

        if on_update:
            on_update(
                status=f"Indexing remote cache: {data_root}",
                increment=False,
                force=True,
            )

        # Fetch remote project refs per peer+subdir
        for peer in self.config.peers:
            cache_key = (peer, data_root)
            if cache_key not in FolderNode._remote_cache:
                refs = set(discover_remote_projects_under(peer, data_root))
                FolderNode._remote_cache[cache_key] = refs
            for ref in FolderNode._remote_cache[cache_key]:
                self._add_project_from_cache(ref, data_root, on_update=on_update)

        if on_update:
            on_update(status="Scanning folders...", increment=False, force=True)
        self._remote_loaded = True
