from functools import cached_property
from pathlib import Path

from echogit.sync.project_node import ProjectNode
from echogit.sync.rsync_peer_node import RsyncPeerNode


class RsyncProjectNode(ProjectNode):

    @cached_property
    def rsync_path(self) -> Path:
        rel = self.relative_path
        return (self.config.git_path / rel).with_suffix(".rsync")

    def scan(self) -> None:
        self._scan(RsyncPeerNode)
