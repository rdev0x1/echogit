from functools import cached_property
from pathlib import Path

from echogit.node import Node
from echogit.sync.branch_node import BranchNode
from echogit.utils import safe_run_command


class PeerNode(Node):
    """
    Represents one remote peer under a Git project.
    We’ll list all remote branches and make one BranchNode each.
    """

    def __init__(self, path: Path, peer_name: str, **kwargs):
        super().__init__(path, **kwargs)
        self.name = peer_name

    @cached_property
    def git_path(self) -> Path:
        return self.parent.git_path

    def get_icon(self) -> str:
        return "💻"

    def scan(self) -> None:
        self.children.clear()
        for branch in self._fetch_remote_branches():
            child = BranchNode(
                path=self.path,
                branch_name=branch,
                parent=self,
            )
            self.add_child(child)

    def _fetch_remote_branches(self) -> list[str]:

        cmd = ["git", "-C", str(self.path), "branch"]

        success, out = safe_run_command(cmd)
        self.log(out, not success)

        if not success:
            return []

        # Parse branch names from stdout
        branches: list[str] = []
        for line in out.splitlines():
            name = line.strip().lstrip("* ").strip()
            if name:
                branches.append(name)

        return branches

    def sync(self) -> bool:

        # If this project is not cloned, then there is nothing to sync
        if not self.exists_locally:
            return True

        remote = self.config.remote_name
        desired_url = str(self.git_path)
        path = str(self.path)

        # Check if the remote already exists and what URL it has
        success, existing_url = safe_run_command(
            ["git", "-C", str(self.path), "remote", "get-url", remote]
        )
        self.log(existing_url, not success)

        cmds_to_run: list[list[str]] = []

        if success:
            existing_url = existing_url.strip()
            if existing_url != desired_url:
                _cmd = ["git", "-C", path, "remote", "set-url", remote, desired_url]
                cmds_to_run.append(_cmd)
        else:
            # `get-url` failed → remote probably doesn't exist. Add it.
            cmds_to_run.append(
                ["git", "-C", str(self.path), "remote", "add", remote, desired_url]
            )

        cmds_to_run.append(["git", "-C", path, "fetch", remote])

        for cmd in cmds_to_run:
            success, out = safe_run_command(cmd, cwd=path)
            self.log(out, not success)
            if not success:
                return False

        return super().sync()
