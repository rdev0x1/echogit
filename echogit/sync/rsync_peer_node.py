import shlex
from functools import cached_property
from pathlib import Path

from echogit.config import Config
from echogit.sync.peer_node import PeerNode
from echogit.utils import (
    _is_local_peer,
    append_path_suffix,
    is_peer_reachable,
    run_ssh_command,
    safe_run_command,
)


class RsyncPeerNode(PeerNode):
    """
    Represents one remote peer under an Rsync project.
    """

    @cached_property
    def rsync_path(self) -> Path:
        rconfig = (
            self.config
            if self._is_peer_local(self.name)
            else Config.get_config_peer(self.name)
        )
        if rconfig is None or rconfig.git_path is None:
            raise ValueError(f"Cannot fetch config for peer '{self.name}'")
        return append_path_suffix(rconfig.git_path / self.relative_path, ".rsync")

    def _is_peer_local(self, host: str) -> bool:
        return self.config.is_local_peer(host) or _is_local_peer(host)

    def _rsync_location(self, p: Path, *, trailing_slash: bool = False) -> str:
        path = str(p) + ("/" if trailing_slash else "")
        if self._is_peer_local(self.name):
            return path
        return f"{self.name}:{shlex.quote(path)}"

    def _ensure_remote_dir(self, p: Path) -> bool:
        if self._is_peer_local(self.name):
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

            if (
                self.config.ignore_peers_down
                and not self._is_peer_local(self.name)
                and not is_peer_reachable(self.name)
            ):
                self.log(f"peer '{self.name}' unreachable; skipping sync", False)
                return self.skip_sync(on_progress, reason="peer_down")

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
            if self._is_peer_local(host)
            else f"{host}:{shlex.quote(str(remote_repo) + '/')}"
        )
        path = str(self.path) + "/"
        cmd = ["rsync", "-aur", url, path]

        return cmd
