from functools import cached_property
from pathlib import Path
import subprocess

from echogit.node import Node
from echogit.utils import _is_local_peer, safe_run_command


class BranchNode(Node):
    """
    Represents a Git branch within a peer.
    """

    def __init__(self, path: Path, branch_name: str, parent: Node):
        super().__init__(path=path, parent=parent)
        self.name = branch_name
        self.peer_name = parent.name
        self._scanned = True

    def get_icon(self) -> str:
        return "🌿"

    def scan(self, on_update=None):
        self.children.clear()
        self._scanned = True

    @cached_property
    def git_path(self) -> Path:
        return self.parent.git_path

    def _checkout_or_create(self, path: str, remote: str, branch: str):
        ok, _ = safe_run_command(
            ["git", "-C", path, "show-ref", "--verify", f"refs/heads/{branch}"],
            cwd=path,
        )
        remote_ref = f"refs/remotes/{remote}/{branch}"
        if ok:
            safe_run_command(["git", "-C", path, "checkout", branch], cwd=path)
        else:
            safe_run_command(
                ["git", "-C", path, "branch", branch, remote_ref], cwd=path
            )
            safe_run_command(["git", "-C", path, "checkout", branch], cwd=path)

    def _restore_branch(self, path: str, branch: str | None):
        if branch and branch != self.name:
            safe_run_command(["git", "-C", path, "checkout", branch], cwd=path)

    def _is_ancestor(self, path: str, ancestor: str, descendant: str) -> bool:
        cmd = ["git", "-C", path, "merge-base", "--is-ancestor", ancestor, descendant]
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True)
        return result.returncode == 0

    def _rev_parse(self, path: str, ref: str) -> str | None:
        cmd = ["git", "-C", path, "rev-parse", ref]
        result = subprocess.run(cmd, cwd=path, capture_output=True, text=True)
        if result.returncode != 0:
            return None
        return result.stdout.strip()

    def sync(self, on_progress=None) -> bool:
        remote = self.peer_name
        path = str(self.path)
        branch = self.name

        # Remember current branch to restore later
        ok, out = safe_run_command(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], cwd=path
        )
        original_branch = out.strip() if ok else None

        # Only attempt to pull if the branch exists on the remote
        exists = False
        if _is_local_peer(remote):
            exists = True
        else:
            check_cmd = ["git", "-C", path, "ls-remote", "--heads", remote, branch]
            ok, out = safe_run_command(check_cmd, cwd=path)
            exists = ok and out.strip() != ""

        if exists:
            # Checkout or create a local branch that tracks the remote branch
            self._checkout_or_create(path, remote, branch)

            # Fetch only the requested branch, then fast-forward merge it.
            fetch_cmd = ["git", "-C", path, "fetch", remote, branch]
            success, out = safe_run_command(fetch_cmd, cwd=path)
            self.log(out, not success)
            if not success:
                self._restore_branch(path, original_branch)
                if self._current_sync_gen is not None:
                    self.mark_synced(self._current_sync_gen, False)
                return False

            local_ref = f"refs/heads/{branch}"
            remote_ref = f"refs/remotes/{remote}/{branch}"
            if self._is_ancestor(path, remote_ref, local_ref):
                self.log("local ahead of remote; skipping pull", False)
            elif self._is_ancestor(path, local_ref, remote_ref):
                merge_cmd = ["git", "-C", path, "merge", "--ff-only", remote_ref]
                success, out = safe_run_command(merge_cmd, cwd=path)
                self.log(out, not success)
                if not success:
                    self._restore_branch(path, original_branch)
                    self._sync_state = "error"
                    if self._current_sync_gen is not None:
                        self.mark_synced(self._current_sync_gen, False)
                    if on_progress:
                        on_progress(self, False)
                    return False
            else:
                local_sha = self._rev_parse(path, local_ref) or "unknown"
                remote_sha = self._rev_parse(path, remote_ref) or "unknown"
                self.log(
                    f"local and remote diverged ({local_sha} vs {remote_sha})",
                    True,
                )
                self._restore_branch(path, original_branch)
                self._sync_state = "error"
                if self._current_sync_gen is not None:
                    self.mark_synced(self._current_sync_gen, False)
                if on_progress:
                    on_progress(self, False)
                return False
        else:
            # Remote branch not found; skip pulling
            self.log(f"Remote branch {remote}/{branch} not found; skipping pull", False)

        # Auto-commit, if project configured for auto-commit
        if self.relative_path in self.config.auto_commit_projects:
            # git add all changes
            add_cmd = ["git", "-C", path, "add", "-A", "."]
            success, out = safe_run_command(add_cmd, cwd=path)
            self.log(out, not success)
            if not success:
                self._restore_branch(path, original_branch)
                self._sync_state = "error"
                if self._current_sync_gen is not None:
                    self.mark_synced(self._current_sync_gen, False)
                if on_progress:
                    on_progress(self, False)
                return False

            # Check if there are staged changes
            diff_cmd = ["git", "-C", path, "diff", "--cached", "--quiet"]
            diff_result = subprocess.run(
                diff_cmd, cwd=path, capture_output=True, text=True
            )
            if diff_result.returncode == 1:
                commit_cmd = ["git", "-C", path, "commit", "-s", "-m", "auto commit"]
                success, out = safe_run_command(commit_cmd, cwd=path)
                self.log(out, not success)
                if not success:
                    self._restore_branch(path, original_branch)
                    return False
            elif diff_result.returncode != 0:
                out = f"{diff_result.stdout}\n{diff_result.stderr}".strip()
                self.log(f"git diff --cached failed: {out}", True)
                self._restore_branch(path, original_branch)
                self._sync_state = "error"
                if self._current_sync_gen is not None:
                    self.mark_synced(self._current_sync_gen, False)
                if on_progress:
                    on_progress(self, False)
                return False

        # Push current branch back to remote
        push_cmd = ["git", "-C", path, "push", remote, branch]
        success, out = safe_run_command(push_cmd, cwd=path)
        self.log(out, not success)
        self._restore_branch(path, original_branch)
        self._sync_state = "ok" if success else "error"
        if self._current_sync_gen is not None:
            self.mark_synced(self._current_sync_gen, success)
        if on_progress:
            on_progress(self, success)
        return success
