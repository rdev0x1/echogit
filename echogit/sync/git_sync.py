from functools import cached_property
from pathlib import Path

from echogit.sync.git_peer_node import GitPeerNode
from echogit.sync.project_node import ProjectNode
from echogit.utils import safe_run_command


class GitProjectNode(ProjectNode):

    @cached_property
    def git_path(self) -> Path:
        if self.config.git_path is None:
            raise ValueError("git_path is not configured")
        rel = self.relative_path
        return (self.config.git_path / rel).with_suffix(".git")

    def scan(self, on_update=None) -> None:
        self._scan(GitPeerNode, on_update=on_update)
        self._update_dirty_state()
        if on_update:
            on_update(node=self, increment=False)
        self.state.presence.scanned = True

    def _update_dirty_state(self) -> None:
        if not self.state.presence.exists_locally:
            self.state.presence.is_dirty = False
            return

        if not (self.path / ".git").is_dir():
            self.state.presence.is_dirty = False
            return

        # Fast path: check tracked changes only to keep TUI responsive.
        path_str = str(self.path)
        cmd = ["git", "-C", path_str, "status", "--porcelain=v1", "-uno"]
        success, out = safe_run_command(cmd)
        if success:
            self.state.presence.is_dirty = bool(out.strip())
            if not self.state.presence.is_dirty:
                # If tracked changes are clean, check untracked files separately.
                untracked_cmd = [
                    "git",
                    "-C",
                    path_str,
                    "ls-files",
                    "--others",
                    "--exclude-standard",
                ]
                success, out = safe_run_command(untracked_cmd)
                if success:
                    self.state.presence.is_dirty = bool(out.strip())
                else:
                    self.state.log.has_error = True
        else:
            self.state.presence.is_dirty = False
            self.state.log.has_error = True
