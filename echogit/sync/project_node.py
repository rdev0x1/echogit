from echogit.node import Node


class ProjectNode(Node):
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
            return

        config = self.config

        for peer_name in config.peers:
            # only instantiate peers that are both reachable and allowed for this path
            if not config.is_path_allowed(peer_name, self.path):
                continue

            peer_node = cls(path=self.path, peer_name=peer_name, parent=self)
            peer_node.scan(on_update=on_update)
            self.add_child(peer_node)
            if on_update:
                on_update()
