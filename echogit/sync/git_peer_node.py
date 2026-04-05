from functools import cached_property
from pathlib import Path

from echogit.config import Config
from echogit.sync.branch_node import BranchNode
from echogit.sync.peer_node import PeerNode
from echogit.utils import (
    _is_local_peer,
    append_path_suffix,
    is_peer_reachable,
    safe_run_command,
)


class GitPeerNode(PeerNode):
    """
    sync_parallel = False
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
        rconfig = (
            self.config
            if self._is_peer_local(remote)
            else Config.get_config_peer(remote)
        )
        if rconfig is None or rconfig.git_path is None:
            raise ValueError(f"Cannot fetch config for peer '{remote}'")
        return append_path_suffix(rconfig.git_path / self.relative_path, ".git")

    def _is_peer_local(self, host: str) -> bool:
        return self.config.is_local_peer(host) or _is_local_peer(host)

    def _git_location(self, host: str, remote_repo: Path) -> str:
        if self._is_peer_local(host):
            return str(remote_repo)
        return f"{host}:{remote_repo}"

    def scan(self, on_update=None) -> None:
        if self._branches_loaded:
            return
        self._load_branch_nodes(on_update=on_update)

    def _load_branch_nodes(self, on_update=None) -> None:
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
        self.state.presence.scanned = True

    def ensure_scanned(self, on_update=None) -> None:
        if not self._branches_loaded:
            self.scan(on_update=on_update)

    def _fetch_remote_branches(self) -> list[str]:
        ref_prefix = f"refs/remotes/{self.name}"
        cmd = [
            "git",
            "-C",
            str(self.path),
            "for-each-ref",
            "--format=%(refname)",
            ref_prefix,
        ]

        success, out = safe_run_command(cmd)
        self.log(out, not success)

        if not success:
            return []

        branches = set()
        branch_prefix = f"{ref_prefix}/"
        for line in out.splitlines():
            ref = line.strip()
            if not ref.startswith(branch_prefix):
                continue
            branch = ref[len(branch_prefix):]
            if branch and branch != "HEAD":
                branches.add(branch)
        return sorted(branches)

    def sync(self, on_progress=None) -> bool:
        lock = self._get_peer_lock(self.name)
        with lock:
            # If this project is not cloned, then there is nothing to sync
            if not self.state.presence.exists_locally:
                return True

            remote = self.name
            if (
                self.config.ignore_peers_down
                and not self._is_peer_local(remote)
                and not is_peer_reachable(remote)
            ):
                self.log(f"peer '{remote}' unreachable; skipping sync", False)
                return self.skip_sync(on_progress)

            try:
                desired_url = self._git_location(remote, self.git_path)
            except ValueError as e:
                self.log(str(e), True)
                return self._finalize_sync(False, on_progress)
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
                    return self._finalize_sync(False, on_progress)

            self._branches_loaded = False
            self._load_branch_nodes()
            return super().sync(on_progress=on_progress)

    def begin_sync(self) -> int:
        gen = super().begin_sync()
        for child in self.children:
            child.begin_sync()
        return gen

    def get_clone_command(self, rel: Path, remote_base: Path):
        # determine remote bare‐repo root
        # append ".git" suffix on the path
        remote_repo = remote_base / f"{rel}.git"
        host = self.name

        # Build an SSH remote location and clone.
        url = self._git_location(host, remote_repo)
        cmd = ["git", "clone", url, str(self.path)]

        return cmd
