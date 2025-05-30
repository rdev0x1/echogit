from pathlib import Path

from echogit.config import Config
from echogit.node import Node
from echogit.utils import run_ssh_command, safe_run_command


class PeerNode(Node):
    def __init__(self, path: Path, peer_name: str, **kwargs):
        super().__init__(path, **kwargs)
        self.name = peer_name

    def get_icon(self) -> str:
        return "💻"

    def get_clone_command(self, rel: Path, remote_base: Path):
        raise NotImplementedError(
            "get_clone_command()  must be implemented by subclasses"
        )

    def clone(self) -> bool:
        """
        Try cloning this project’s bare‐repo from each host in self.remote_peers.
        Returns True on first success, False on overall failure.
        Logs stdout/stderr in self.log and last error in self.error.
        """
        # the relative path under projects_path (e.g. "foo/bar")
        rel = self.relative_path

        # make sure parent dir exists
        parent_dir = self.path.parent
        parent_dir.mkdir(parents=True, exist_ok=True)

        host = self.name

        # fetch that host’s config.ini
        success, cfg_txt = run_ssh_command(host, f"cat {Config.CONFIG_FILE}")
        self.log(cfg_txt, not success)
        if success is False:
            return False

        rconfig = Config.load_from_buffer(cfg_txt)
        remote_base = rconfig.git_path

        cmd = self.get_clone_command(rel, remote_base)

        success, out = safe_run_command(cmd, cwd=str(parent_dir))
        self.log(out, not success)

        return success
