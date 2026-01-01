from functools import cached_property
from pathlib import Path
import subprocess

from echogit.node import Node
from echogit.utils import _is_local_peer, is_peer_reachable, safe_run_command


class BranchNode(Node):
    """
    Represents a Git branch within a peer.
    """

    def __init__(self, path: Path, branch_name: str, parent: Node):
        super().__init__(path=path, parent=parent)
        self.name = branch_name
        self.peer_name = parent.name
        self.state.presence.scanned = True

    def get_icon(self) -> str:
        return "🌿"

    def scan(self, on_update=None):
        self.children.clear()
        self.state.presence.scanned = True

    @cached_property
    def git_path(self) -> Path:
        return self.parent.git_path

    def _checkout_or_create(self, path: str, remote: str, branch: str) -> bool:
        ok, _ = safe_run_command(
            ["git", "-C", path, "show-ref", "--verify", f"refs/heads/{branch}"],
            cwd=path,
        )
        remote_ref = f"refs/remotes/{remote}/{branch}"
        if ok:
            success, out = safe_run_command(
                ["git", "-C", path, "checkout", branch], cwd=path
            )
            self.log(out, not success)
            return success

        success, out = safe_run_command(
            ["git", "-C", path, "branch", branch, remote_ref], cwd=path
        )
        self.log(out, not success)
        if not success:
            return False
        success, out = safe_run_command(
            ["git", "-C", path, "checkout", branch], cwd=path
        )
        self.log(out, not success)
        return success

    def _restore_branch(self, path: str, branch: str | None):
        if branch and branch != self.name:
            safe_run_command(["git", "-C", path, "checkout", branch], cwd=path)

    def _is_ancestor(self, path: str, ancestor: str, descendant: str) -> bool:
        cmd = ["git", "-C", path, "merge-base", "--is-ancestor", ancestor, descendant]
        returncode, _, _ = self._run_git(path, cmd)
        return returncode == 0

    def _rev_parse(self, path: str, ref: str) -> str | None:
        cmd = ["git", "-C", path, "rev-parse", ref]
        returncode, stdout, _ = self._run_git(path, cmd)
        if returncode != 0:
            return None
        return stdout.strip()

    def _run_git(self, path: str, cmd: list[str]) -> tuple[int, str, str]:
        try:
            result = subprocess.run(
                cmd, cwd=path, capture_output=True, text=True, check=False
            )
        except FileNotFoundError as e:
            self.log(f"git not found: {e}", True)
            return 127, "", str(e)
        return result.returncode, result.stdout, result.stderr

    def _finish_sync(
        self, success: bool, path: str, original_branch: str | None, on_progress
    ) -> bool:
        self._restore_branch(path, original_branch)
        return self._finalize_sync(success, on_progress)

    def _fail_sync(self, path: str, original_branch: str | None, on_progress) -> bool:
        return self._finish_sync(False, path, original_branch, on_progress)

    def _current_branch(self, path: str) -> str | None:
        ok, out = safe_run_command(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], cwd=path
        )
        return out.strip() if ok else None

    def _remote_branch_exists(self, path: str, remote: str, branch: str) -> bool:
        if _is_local_peer(remote):
            return True
        check_cmd = ["git", "-C", path, "ls-remote", "--heads", remote, branch]
        ok, out = safe_run_command(check_cmd, cwd=path)
        return ok and out.strip() != ""

    def _fetch_remote_branch(self, path: str, remote: str, branch: str) -> bool:
        fetch_cmd = ["git", "-C", path, "fetch", remote, branch]
        success, out = safe_run_command(fetch_cmd, cwd=path)
        self.log(out, not success)
        return success

    def _refs_match(self, path: str, local_ref: str, remote_ref: str) -> bool:
        local_sha = self._rev_parse(path, local_ref)
        remote_sha = self._rev_parse(path, remote_ref)
        if not local_sha or not remote_sha:
            return False
        return local_sha == remote_sha

    def _fast_forward(
        self, path: str, local_ref: str, remote_ref: str
    ) -> bool:
        if self._is_ancestor(path, remote_ref, local_ref):
            self.log("local ahead of remote; skipping pull", False)
            return True
        if self._is_ancestor(path, local_ref, remote_ref):
            merge_cmd = ["git", "-C", path, "merge", "--ff-only", remote_ref]
            success, out = safe_run_command(merge_cmd, cwd=path)
            self.log(out, not success)
            return success
        local_sha = self._rev_parse(path, local_ref) or "unknown"
        remote_sha = self._rev_parse(path, remote_ref) or "unknown"
        self.log(
            f"local and remote diverged ({local_sha} vs {remote_sha})",
            True,
        )
        return False

    def _has_staged_changes(self, path: str) -> bool | None:
        diff_cmd = ["git", "-C", path, "diff", "--cached", "--quiet"]
        returncode, stdout, stderr = self._run_git(path, diff_cmd)
        if returncode == 0:
            return False
        if returncode == 1:
            return True
        out = f"{stdout}\n{stderr}".strip()
        self.log(f"git diff --cached failed: {out}", True)
        return None

    def _auto_commit(
        self, path: str, original_branch: str | None, on_progress
    ) -> bool:
        add_cmd = ["git", "-C", path, "add", "-A", "."]
        success, out = safe_run_command(add_cmd, cwd=path)
        self.log(out, not success)
        if not success:
            return self._fail_sync(path, original_branch, on_progress)

        changes = self._has_staged_changes(path)
        if changes is None:
            return self._fail_sync(path, original_branch, on_progress)
        if changes:
            commit_cmd = ["git", "-C", path, "commit", "-s", "-m", "auto commit"]
            success, out = safe_run_command(commit_cmd, cwd=path)
            self.log(out, not success)
            if not success:
                return self._fail_sync(path, original_branch, on_progress)
        return True

    def _push_branch(
        self, path: str, original_branch: str | None, on_progress
    ) -> bool:
        push_cmd = ["git", "-C", path, "push", self.peer_name, self.name]
        success, out = safe_run_command(push_cmd, cwd=path)
        self.log(out, not success)
        return self._finish_sync(success, path, original_branch, on_progress)

    def sync(self, on_progress=None) -> bool:
        remote = self.peer_name
        path = str(self.path)
        branch = self.name

        # Remember current branch to restore later
        original_branch = self._current_branch(path)

        # Only attempt to pull if the branch exists on the remote
        if self._remote_branch_exists(path, remote, branch):
            if self.config.ignore_peers_down and not _is_local_peer(remote):
                if not is_peer_reachable(remote):
                    self.log(f"peer '{remote}' unreachable; skipping pull", False)
                    return self.skip_sync(on_progress)
            local_ref = f"refs/heads/{branch}"
            remote_ref = f"refs/remotes/{remote}/{branch}"

            # Fetch only the requested branch so the remote ref is up to date.
            if not self._fetch_remote_branch(path, remote, branch):
                return self._fail_sync(path, original_branch, on_progress)

            # If refs already match, avoid checkout to preserve local changes.
            if self._refs_match(path, local_ref, remote_ref):
                self.log("local and remote refs match; skipping checkout", False)
                return self._finish_sync(True, path, original_branch, on_progress)

            # Checkout or create a local branch that tracks the remote branch
            if not self._checkout_or_create(path, remote, branch):
                return self._fail_sync(path, original_branch, on_progress)

            if not self._fast_forward(path, local_ref, remote_ref):
                return self._fail_sync(path, original_branch, on_progress)
        else:
            # Remote branch not found; skip pulling
            self.log(f"Remote branch {remote}/{branch} not found; skipping pull", False)

        # Auto-commit, if project configured for auto-commit
        if self.relative_path in self.config.auto_commit_projects:
            if not self._auto_commit(path, original_branch, on_progress):
                return False

        # Push current branch back to remote
        return self._push_branch(path, original_branch, on_progress)
