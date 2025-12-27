from functools import cached_property
from pathlib import Path

from echogit.sync.peer_node import PeerNode
from echogit.utils import safe_run_command


class RsyncPeerNode(PeerNode):
    """
    Represents one remote peer under an Rsync project.
    """

    @cached_property
    def rsync_path(self) -> Path:
        return self.parent.rsync_path

    def sync(self, on_progress=None) -> bool:
        lock = self._get_peer_lock(self.name)
        with lock:
            # If this project is not cloned, then there is nothing to sync
            if not self.state.presence.exists_locally:
                return True

            path = str(self.path) + "/"
            rsync_path = str(self.rsync_path)
            cmd = [
                "rsync",
                "-aur",
                "--exclude",
                ".echogit/",
                "--exclude",
                ".rsync/",
                path,
                rsync_path,
            ]
            success, out = safe_run_command(cmd)
            self.log(out, not success)
            return self._finalize_sync(success, on_progress)

    def get_clone_command(self, rel: Path, remote_base: Path):
        # determine remote bare‐repo root
        # append ".rsync" suffix on the path
        remote_repo = remote_base / f"{rel}.rsync"
        host = self.name

        # build an SSH URL and clone
        url = f"{host}:{remote_repo}"
        path = str(self.path) + "/"
        cmd = ["rsync", "-aur", "-e", url, path]

        return cmd
