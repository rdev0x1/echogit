from functools import cached_property
from pathlib import Path

from echogit.node import Node


class ProjectNode(Node):
    sync_parallel = False

    @cached_property
    def git_path(self) -> Path:
        raise NotImplementedError("ProjectNode has no git_path")

    def ensure_scanned(self, on_update=None) -> None:
        if not self.state.presence.scanned:
            self.scan(on_update=on_update)

    def begin_sync(self) -> int:
        gen = super().begin_sync()
        for child in self.children:
            child.begin_sync()
        return gen

    def get_icon(self) -> str:
        return "📦" if self.state.presence.exists_locally else "☁️"

    def clone(self) -> bool:
        """
        Try cloning this project’s bare‐repo from each peer node.
        Returns True on first success, False on overall failure.
        Logs stdout/stderr in self.log and last error in self.error.
        """
        for peer_node in self.children:
            success = peer_node.clone()
            if success:
                self.state.presence.exists_locally = True
                return True
        return False

    def _scan(self, cls, on_update=None) -> None:
        self.children.clear()

        config = self.config
        peer_names = (
            list(self.state.presence.remote_peers)
            if not self.state.presence.exists_locally
            and self.state.presence.remote_peers
            else list(config.peers)
        )

        for peer_name in peer_names:
            # only instantiate peers that are both reachable and allowed for this path
            if not config.is_path_allowed(peer_name, self.path):
                continue

            peer_node = cls(path=self.path, peer_name=peer_name, parent=self)
            if self.state.presence.exists_locally and not getattr(
                cls, "defer_scan", False
            ):
                peer_node.scan(on_update=on_update)
            self.add_child(peer_node)
            if on_update:
                on_update(node=peer_node, increment=False)

        self.log(f"scan done: {len(self.children)} peer(s)")
        self.state.presence.scanned = True
