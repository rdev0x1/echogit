from functools import cached_property
from pathlib import Path

from echogit.node import Node
from echogit.utils import safe_run_command


class BranchNode(Node):
    """
    Represents a Git branch within a peer.
    """

    def __init__(self, path: Path, branch_name: str, parent: Node):
        super().__init__(path=path, parent=parent)
        self.name = branch_name
        self.peer_name = parent.name

    def get_icon(self) -> str:
        return "🌿"

    def scan(self):
        self.children.clear()

    @cached_property
    def git_path(self) -> Path:
        return self.parent.git_path

    def sync(self) -> bool:
        remote = self.peer_name

        cmds = [
            # ["git", "-C", str(self.path), "merge", f"{self.peer_name}/{self.name}"],
            ["git", "-C", str(self.path), "push", remote, self.name],
        ]

        for cmd in cmds:
            success, out = safe_run_command(cmd, cwd=str(self.path))
            self.log(out, not success)
            if not success:
                return False

        return True
