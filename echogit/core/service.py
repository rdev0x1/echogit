from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from typing import Callable

from echogit.config import Config
from echogit.core.models import ProjectItem, SyncProgress, SyncResult
from echogit.discovery import ProjectRef, discover_local_projects, discover_remote_projects
from echogit.node import Node
from echogit.node_factory import from_path
from echogit.sync.git_sync import GitProjectNode
from echogit.sync.project_node import ProjectNode
from echogit.sync.rsync_sync import RsyncProjectNode


ProgressCallback = Callable[[SyncProgress], None]


class EchogitService:
    """
    Frontend-facing API for Echogit operations.
    """

    REMOTE_LIST_WORKERS = 4

    def __init__(self, config: Config):
        self.config = config

    def list_projects(self, root: Path | None = None) -> list[ProjectItem]:
        scan_root = Path(root or self.config.projects_path)
        return [
            _project_item_from_ref(ref)
            for ref in discover_local_projects(scan_root)
        ]

    def list_remote_projects(
        self,
        peers: list[str] | None = None,
    ) -> dict[str, list[ProjectItem]]:
        peer_names = list(peers if peers is not None else self.config.peers)
        if not peer_names:
            return {}

        max_workers = min(self.REMOTE_LIST_WORKERS, len(peer_names))
        remote: dict[str, list[ProjectItem]] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                peer: executor.submit(self._list_one_remote, peer)
                for peer in peer_names
            }
            for peer in peer_names:
                try:
                    remote[peer] = futures[peer].result()
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error("list-remote failed for %s: %s", peer, exc)
                    remote[peer] = []
        return remote

    def build_tree(self, root: Path | None = None) -> Node:
        scan_root = Path(root or self.config.projects_path)
        root_node = from_path(scan_root, config=self.config)
        root_node.scan()
        return root_node

    def sync(
        self,
        root: Path | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> SyncResult:
        root_node = self.build_tree(root)

        def _on_node_progress(node: Node, ok: bool) -> None:
            if on_progress is None or not isinstance(node, ProjectNode):
                return
            on_progress(_sync_progress_from_project(node, ok))

        ok = root_node.sync(
            on_progress=_on_node_progress if on_progress is not None else None
        )
        return SyncResult(ok=ok, root=root_node.path)

    def _list_one_remote(self, peer_name: str) -> list[ProjectItem]:
        return [
            _project_item_from_ref(ref)
            for ref in discover_remote_projects(peer_name)
        ]


def _project_item_from_ref(ref: ProjectRef) -> ProjectItem:
    return ProjectItem(rel=ref.rel, type=ref.type)


def _sync_progress_from_project(node: ProjectNode, ok: bool) -> SyncProgress:
    if isinstance(node, GitProjectNode):
        sync_type = "git"
    elif isinstance(node, RsyncProjectNode):
        sync_type = "rsync"
    else:
        sync_type = "project"
    return SyncProgress(
        rel=node.relative_path,
        type=sync_type,
        ok=ok,
        dirty=node.is_dirty(),
        sync_state=node.sync_state(),
        exists_locally=node.state.presence.exists_locally,
    )
