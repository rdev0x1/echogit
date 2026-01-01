from pathlib import Path
import threading

from echogit.config import Config
from echogit.node import Node
from echogit.utils import run_ssh_command, safe_run_command


class PeerNode(Node):
    PEER_MAX_CONCURRENCY = 2
    _peer_locks: dict[str, threading.Semaphore] = {}
    _peer_lock_guard = threading.Lock()

    def __init__(self, path: Path, peer_name: str, **kwargs):
        super().__init__(path, **kwargs)
        self.name = peer_name

    def get_icon(self) -> str:
        return "💻"

    def get_clone_command(self, rel: Path, remote_base: Path) -> list[str]:
        raise NotImplementedError(
            "get_clone_command()  must be implemented by subclasses"
        )

    def clone(self) -> bool:
        """
        Try cloning this project’s bare-repo from this peer host.
        Returns True on success, False on failure.
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
        if not success:
            return False

        rconfig = Config.load_from_buffer(cfg_txt)
        remote_base = rconfig.git_path
        if remote_base is None:
            self.log("remote config missing git_path", True)
            return False

        cmd = self.get_clone_command(rel, remote_base)

        success, out = safe_run_command(cmd, cwd=str(parent_dir))
        self.log(out, not success)

        return success

    @classmethod
    def _get_peer_lock(cls, peer_name: str) -> threading.Semaphore:
        with cls._peer_lock_guard:
            if peer_name not in cls._peer_locks:
                cls._peer_locks[peer_name] = threading.Semaphore(
                    cls.PEER_MAX_CONCURRENCY
                )
            return cls._peer_locks[peer_name]
