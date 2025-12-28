from echogit.node import Node


class ProjectNode(Node):
    sync_parallel = False
    def ensure_scanned(self, on_update=None) -> None:
        if not self._scanned:
            self.scan(on_update=on_update)

    def begin_sync(self) -> int:
        gen = super().begin_sync()
        for child in self.children:
            child.begin_sync()
        return gen

    def get_icon(self) -> str:
        return "📦" if self.exists_locally else "☁️"

    def clone(self) -> bool:
        """
        Try cloning this project’s bare‐repo from each host in self.remote_peers.
        Returns True on first success, False on overall failure.
        Logs stdout/stderr in self.log and last error in self.error.
        """
        for peer_node in self.children:
            success = peer_node.clone()
            if success:
                self.exists_locally = True
                return True
        return False

    def _scan(self, cls, on_update=None) -> None:
        self.children.clear()

        # Remote project: nothing to do until the user decide to clone it
        if self.exists_locally is False:
            self.log("scan skipped: project not cloned")
            self._scanned = True
            return

        config = self.config

        for peer_name in config.peers:
            # only instantiate peers that are both reachable and allowed for this path
            if not config.is_path_allowed(peer_name, self.path):
                continue

            peer_node = cls(path=self.path, peer_name=peer_name, parent=self)
            if not getattr(cls, "defer_scan", False):
                peer_node.scan(on_update=on_update)
            self.add_child(peer_node)
            if on_update:
                on_update(node=peer_node, increment=False)

        self.log(f"scan done: {len(self.children)} peer(s)")
        self._scanned = True
