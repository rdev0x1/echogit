from functools import cached_property
from pathlib import Path

from echogit.sync.git_peer_node import GitPeerNode
from echogit.sync.project_node import ProjectNode


class GitProjectNode(ProjectNode):

    @cached_property
    def git_path(self) -> Path:
        rel = self.relative_path
        return (self.config.git_path / rel).with_suffix(".git")

    def scan(self, on_update=None) -> None:
        self._scan(GitPeerNode, on_update=on_update)
