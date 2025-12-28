from functools import cached_property
from pathlib import Path

from echogit.config import Config
from echogit.sync.branch_node import BranchNode
from echogit.sync.peer_node import PeerNode
from echogit.utils import safe_run_command


class GitPeerNode(PeerNode):
    """
    Represents one remote peer under a Git project.
    We’ll list all remote branches and make one BranchNode each.
    """
    defer_scan = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._branches_loaded = False

    @cached_property
    def git_path(self) -> Path:
        remote = self.name
        rconfig = Config.get_config_peer(remote)
        if rconfig is None or rconfig.git_path is None:
            raise ValueError(f"Cannot fetch config for peer '{remote}'")
        return rconfig.git_path / self.relative_path.with_suffix(".git")

    def scan(self, on_update=None) -> None:
        if self._branches_loaded:
            return
        self.children.clear()
        for branch in self._fetch_remote_branches():
            child = BranchNode(
                path=self.path,
                branch_name=branch,
                parent=self,
            )
            self.add_child(child)
            child.log("branch discovered")
            if on_update:
                on_update(node=child, increment=False)
        self.log(f"scan done: {len(self.children)} branch(es)")
        self._branches_loaded = True
        self._scanned = True

    def ensure_scanned(self, on_update=None) -> None:
        if not self._branches_loaded:
            self.scan(on_update=on_update)

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

        remote = self.name
        rconfig = Config.get_config_peer(remote)
        desired_url = f"ssh://{remote}:{str(self.git_path)}"
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

    def get_clone_command(self, rel: Path, remote_base: Path):
        # determine remote bare‐repo root
        # append ".git" suffix on the path
        remote_repo = remote_base / f"{rel}.git"
        host = self.name

        # build an SSH URL and clone
        url = f"ssh://{host}:{remote_repo}"
        cmd = ["git", "clone", url, str(self.path)]

        return cmd
