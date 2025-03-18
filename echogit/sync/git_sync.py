from functools import cached_property
from pathlib import Path

from echogit.node import Node
from echogit.sync.peer_node import PeerNode
from echogit.utils import safe_run_command


class GitProjectNode(Node):

    @cached_property
    def git_path(self) -> Path:
        rel = self.relative_path
        return (self.config.git_path / rel).with_suffix(".git")

    def clone(self) -> bool:
        """
        Try cloning this project’s bare‐repo.
        Returns True on first success, False on overall failure.
        Logs stdout/stderr in self.log and last error in self.error.
        """
        # the relative path under projects_path (e.g. "foo/bar")
        rel = self.path.relative_to(self.config.projects_path)

        # make sure parent dir exists
        parent_dir = self.path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        #  determine bare‐repo root
        bare_root = self.config.git_path
        if bare_root:
            remote_base = Path(bare_root).expanduser()
            # append ".git" suffix on the path
            remote_repo = remote_base / f"{rel}.git"
        else:
            # fallback to their projects_path if they have no git_path
            data_root = Path("~/echogit_git").expanduser()
            remote_repo = data_root / rel

        cmd = ["git", "clone", remote_repo, str(self.path)]
        success, _ = safe_run_command(cmd, cwd=str(parent_dir))

        if success:
            self.exists_locally = True
            return True

        # record this host’s failure
        return False

    def scan(self) -> None:
        self.children.clear()

        peer_node = PeerNode(path=self.path, peer_name="localhost", parent=self)
        peer_node.scan()
        self.add_child(peer_node)
