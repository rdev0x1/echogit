"""
FolderNode: scans directories for Git/Rsync projects or subfolders.
Uses class-level caches to avoid redundant discovery.
"""

from concurrent.futures import ThreadPoolExecutor
from functools import cached_property
import threading
import time
from pathlib import Path
from typing import Dict, Iterator, Set

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
    _remote_cache: Dict[tuple[str, Path], tuple[float, Set[ProjectRef]]] = {}
    _local_cache: Set[ProjectRef] = set()
    node_by_relpath: Dict[Path, Node] = {}
    _index_lock = threading.Lock()
    _cache_lock = threading.Lock()

    # marker file to skip a folder subtree
    SKIP_MARKER = ".echogitskip"
    REMOTE_CACHE_TTL = 60.0
    SCAN_WORKERS = 4

    def __init__(self, path: Path, **kwargs):
        super().__init__(path, **kwargs)
        self._remote_loaded = False

    @cached_property
    def is_folder(self) -> bool:
        # override Node.is_folder if you want to treat
        # bare-repo dirs (.git, .rsync) as non-folders here
        return True

    def get_icon(self) -> str:
        return "📁" if self.state.presence.collapse else "📂"

    @cached_property
    def git_path(self) -> Path:
        """FolderNode does not implement git_path."""
        raise NotImplementedError("FolderNode has no git_path")

    def scan(self, on_update=None) -> None:
        self.children.clear()

        rel_self = self._prepare_scan(on_update=on_update)
        if rel_self is None:
            return

        scan_targets = self._scan_local_children(on_update=on_update)
        self._scan_children(scan_targets, on_update=on_update)

        # Discover missing projects from caches
        if self.parent is None:
            self._add_local_projects_from_cache(rel_self, on_update=on_update)

        self.log(f"scan done: {len(self.children)} child node(s)")
        self.state.presence.scanned = True

    def _prepare_scan(self, on_update=None) -> Path | None:
        # Skip whole subtree if marker file present
        if (self.path / self.SKIP_MARKER).exists():
            self.log(f"scan skipped: {self.SKIP_MARKER} present")
            self.state.presence.scanned = True
            return None

        if self.parent is None and on_update:
            on_update(status="Scanning folders...", increment=False, force=True)

        # Index this folder only if it’s inside an allowed root
        rel_self = self._rel_from_roots(self.path)
        if rel_self is None:
            self.log("scan skipped: outside configured roots")
            self.state.presence.scanned = True
            return None
        with FolderNode._index_lock:
            FolderNode.node_by_relpath[rel_self] = self
        return rel_self

    def _scan_local_children(self, on_update=None) -> list[Node]:
        scan_targets: list[Node] = []
        for child in self._iter_child_dirs():
            target = child.resolve()
            child_rel = self._rel_from_roots(target)
            if child_rel is None:
                continue
            if (target / self.SKIP_MARKER).exists():
                continue
            existing = self._reuse_existing_node(child_rel, on_update=on_update)
            if existing is not None:
                scan_targets.append(existing)
                continue
            if self._is_ancestor_path(target):
                continue
            node = self._build_child_node(target)
            self._register_child(child_rel, node, on_update=on_update)
            scan_targets.append(node)
        return scan_targets

    def _iter_child_dirs(self) -> Iterator[Path]:
        for child in sorted(self.path.iterdir()):
            if not child.is_dir() or child.name in {".git", ".rsync", ".echogit"}:
                continue
            yield child

    def _reuse_existing_node(self, child_rel: Path, on_update=None) -> Node | None:
        with FolderNode._index_lock:
            existing = FolderNode.node_by_relpath.get(child_rel)
        if existing is None:
            return None
        existing.parent = self
        existing.state.presence.exists_locally = True
        self.add_child(existing)
        if on_update:
            on_update(node=existing)
        return existing

    def _build_child_node(self, target: Path) -> Node:
        if (target / ".git").is_dir() or target.suffix == ".git":
            return GitProjectNode(path=target, parent=self)
        if (target / ".rsync").is_dir() or target.suffix == ".rsync":
            return RsyncProjectNode(path=target, parent=self)
        return FolderNode(path=target, parent=self)

    def _register_child(self, child_rel: Path, node: Node, on_update=None) -> None:
        node.state.presence.exists_locally = True
        self.add_child(node)
        if on_update:
            on_update(node=node)
        with FolderNode._index_lock:
            FolderNode.node_by_relpath[child_rel] = node

    def _scan_children(self, scan_targets: list[Node], on_update=None) -> None:
        if not scan_targets:
            return
        if self.SCAN_WORKERS <= 1:
            for node in scan_targets:
                node.scan(on_update=on_update)
            return
        with ThreadPoolExecutor(max_workers=self.SCAN_WORKERS) as executor:
            futures = [
                executor.submit(node.scan, on_update=on_update)
                for node in scan_targets
            ]
            for future in futures:
                future.result()

    def ensure_scanned(self, on_update=None) -> None:
        if not self.state.presence.scanned:
            self.scan(on_update=on_update)
        if not self._remote_loaded:
            self._load_remote_projects_for_node(on_update=on_update)

    def _add_local_projects_from_cache(
        self, data_root: Path, on_update=None
    ) -> None:
        if not FolderNode._local_cache:
            if on_update:
                on_update(status="Indexing cache...", increment=False, force=True)
            for ref in discover_local_projects(self.path):
                with FolderNode._cache_lock:
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

        with FolderNode._index_lock:
            if rel_path == Path(".") or rel_path in FolderNode.node_by_relpath:
                return True

        ret = self._ensure_parents(rel_path.parent, data_root, on_update=on_update)
        if ret is False:
            return False

        with FolderNode._index_lock:
            parent_node = FolderNode.node_by_relpath[rel_path.parent]

        # Only create childs node under folder node. We dont want childs under
        # projects node.
        if not parent_node.is_folder:
            return False

        abs_path = (self.config.projects_path / rel_path).resolve()

        node = FolderNode(path=abs_path, parent=parent_node)
        node.state.presence.exists_locally = abs_path.is_dir()
        node.state.presence.scanned = True
        parent_node.add_child(node)
        with FolderNode._index_lock:
            FolderNode.node_by_relpath[rel_path] = node
        if on_update:
            on_update(node=node, increment=False)
        return True

    def _add_project_from_cache(
        self, ref: ProjectRef, data_root: Path, on_update=None
    ) -> None:
        with FolderNode._index_lock:
            if ref.rel in FolderNode.node_by_relpath:
                return  # Already exists locally

        # process only subfolders of data_root
        if not ref.rel.is_relative_to(data_root):
            return

        # Recursively ensure parent folders exist
        ret = self._ensure_parents(ref.rel.parent, data_root, on_update=on_update)
        if ret is False:
            return

        with FolderNode._index_lock:
            parent_node = FolderNode.node_by_relpath[ref.rel.parent]
        abs_path = (self.config.projects_path / ref.rel).resolve()

        if ref.type == "git":
            node = GitProjectNode(path=abs_path, parent=parent_node)
        elif ref.type == "rsync":
            node = RsyncProjectNode(path=abs_path, parent=parent_node)
        else:
            return  # Skip unknown type

        node.state.presence.exists_locally = abs_path.is_dir()
        parent_node.add_child(node)
        parent_node.state.presence.scanned = True
        if on_update:
            on_update(node=node)
        node.scan(on_update=on_update)
        with FolderNode._index_lock:
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
            with FolderNode._cache_lock:
                cached = FolderNode._remote_cache.get(cache_key)
            now = time.monotonic()
            if cached is None or now - cached[0] > self.REMOTE_CACHE_TTL:
                refs = set(discover_remote_projects_under(peer, data_root))
                with FolderNode._cache_lock:
                    FolderNode._remote_cache[cache_key] = (now, refs)
                    cached = FolderNode._remote_cache[cache_key]
            for ref in cached[1]:
                self._add_project_from_cache(ref, data_root, on_update=on_update)

        if on_update:
            on_update(status="Scanning folders...", increment=False, force=True)
        self._remote_loaded = True
