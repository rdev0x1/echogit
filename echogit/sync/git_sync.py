from functools import cached_property
from pathlib import Path

from echogit.config import Config
from echogit.node import Node
from echogit.sync.peer_node import PeerNode
from echogit.utils import run_ssh_command, safe_run_command


class GitProjectNode(Node):

    @cached_property
    def git_path(self) -> Path:
        rel = self.relative_path
        return (self.config.git_path / rel).with_suffix(".git")

    def get_icon(self) -> str:
        return "📦" if self.exists_locally else "☁️"

    def clone(self) -> bool:
        """
        Try cloning this project’s bare‐repo from each host in self.remote_peers.
        Returns True on first success, False on overall failure.
        Logs stdout/stderr in self.log and last error in self.error.
        """
        # the relative path under projects_path (e.g. "foo/bar")
        rel = self.path.relative_to(self.config.projects_path)

        # make sure parent dir exists
        parent_dir = self.path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        for host in self.remote_peers:
            # fetch that host’s config.ini
            success, cfg_txt = run_ssh_command(host, f"cat {Config.CONFIG_FILE}")
            self.log(cfg_txt, not success)
            if success is False:
                continue
            rconfig = Config.load_from_buffer(cfg_txt)
            remote_base = rconfig.git_path

            # determine remote bare‐repo root
            # append ".git" suffix on the path
            remote_repo = remote_base / f"{rel}.git"

            # build an SSH URL and clone
            url = f"ssh://{host}:{remote_repo}"
            cmd = ["git", "clone", url, str(self.path)]
            success, out = safe_run_command(cmd, cwd=str(parent_dir))
            self.log(out, not success)

            if success:
                self.exists_locally = True
                return True

        return False

    def scan(self) -> None:
        self.children.clear()

        config = self.config

        for peer_name in config.peers:
            # ▼ only instantiate peers that are both reachable and allowed for this path
            if not config.is_path_allowed(peer_name, self.path):
                continue

            peer_node = PeerNode(path=self.path, peer_name=peer_name, parent=self)
            peer_node.scan()
            self.add_child(peer_node)
