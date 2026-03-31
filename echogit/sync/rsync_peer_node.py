import shlex
from functools import cached_property
from pathlib import Path

from echogit.config import Config
from echogit.sync.peer_node import PeerNode
from echogit.utils import _is_local_peer, run_ssh_command, safe_run_command


class RsyncPeerNode(PeerNode):
    """
    Represents one remote peer under an Rsync project.
    """

    @cached_property
    def rsync_path(self) -> Path:
        rconfig = Config.get_config_peer(self.name)
        if rconfig is None or rconfig.git_path is None:
            raise ValueError(f"Cannot fetch config for peer '{self.name}'")
        return (rconfig.git_path / self.relative_path).with_suffix(".rsync")

    def _rsync_location(self, p: Path, *, trailing_slash: bool = False) -> str:
        path = str(p) + ("/" if trailing_slash else "")
        if _is_local_peer(self.name):
            return path
        return f"{self.name}:{shlex.quote(path)}"

    def _ensure_remote_dir(self, p: Path) -> bool:
        if _is_local_peer(self.name):
            try:
                p.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                self.log(f"failed to create rsync destination {p}: {exc}", True)
                return False
            return True

        success, out = run_ssh_command(
            self.name,
            f"mkdir -p {shlex.quote(str(p))}",
        )
        self.log(out, not success)
        return success

    def sync(self, on_progress=None) -> bool:
        lock = self._get_peer_lock(self.name)
        with lock:
            # If this project is not cloned, then there is nothing to sync
            if not self.state.presence.exists_locally:
                return True

            try:
                rsync_path = self.rsync_path
            except ValueError as exc:
                self.log(str(exc), True)
                return self._finalize_sync(False, on_progress)

            if not self._ensure_remote_dir(rsync_path):
                return self._finalize_sync(False, on_progress)

            path = str(self.path) + "/"
            target = self._rsync_location(rsync_path, trailing_slash=True)
            cmd = [
                "rsync",
                "-aur",
                "--exclude",
                ".echogit/",
                "--exclude",
                ".rsync/",
                path,
                target,
            ]
            success, out = safe_run_command(cmd)
            self.log(out, not success)
            return self._finalize_sync(success, on_progress)

    def get_clone_command(self, rel: Path, remote_base: Path):
        # determine remote bare‐repo root
        # append ".rsync" suffix on the path
        remote_repo = remote_base / f"{rel}.rsync"
        host = self.name

        # Build an rsync remote source. The host can be an SSH config alias.
        url = (
            str(remote_repo) + "/"
            if _is_local_peer(host)
            else f"{host}:{shlex.quote(str(remote_repo) + '/')}"
        )
        path = str(self.path) + "/"
        cmd = ["rsync", "-aur", url, path]

        return cmd
