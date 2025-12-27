from functools import cached_property
from pathlib import Path

from echogit.node import Node
from echogit.utils import safe_run_command


class BranchNode(Node):
    """
    Represents a Git branch within a peer.
    """

    def __init__(self, path: Path, branch_name: str, parent: Node):
        super().__init__(path=path, parent=parent)
        self.name = branch_name
        self.peer_name = parent.name

    def get_icon(self) -> str:
        return "🌿"

    def scan(self, on_update=None):
        self.children.clear()

    @cached_property
    def git_path(self) -> Path:
        return self.parent.git_path

    def _checkout_or_create(self, path: str, remote: str, branch: str):
        ok, _ = safe_run_command(
            ["git", "-C", path, "rev-parse", "--verify", branch], cwd=path
        )
        if ok:
            safe_run_command(["git", "-C", path, "checkout", branch], cwd=path)
        else:
            safe_run_command(
                ["git", "-C", path, "checkout", "-b", branch, f"{remote}/{branch}"],
                cwd=path,
            )

    def _restore_branch(self, path: str, branch: str | None):
        if branch and branch != self.name:
            safe_run_command(["git", "-C", path, "checkout", branch], cwd=path)

    def sync(self) -> bool:
        remote = self.peer_name
        path = str(self.path)
        branch = self.name

        # Remember current branch to restore later
        ok, out = safe_run_command(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"], cwd=path
        )
        original_branch = out.strip() if ok else None

        # Only attempt to pull if the branch actually exists on the remote
        check_cmd = ["git", "-C", path, "ls-remote", "--heads", remote, branch]
        exists, out = safe_run_command(check_cmd, cwd=path)
        if exists and out.strip():
            # Checkout or create a local branch that tracks the remote branch
            self._checkout_or_create(path, remote, branch)

            # Pull latest remote changes into the same-named local branch
            pull_cmd = ["git", "-C", path, "pull", remote, branch]
            success, out = safe_run_command(pull_cmd, cwd=path)
            self.log(out, not success)
            if not success:
                self._restore_branch(path, original_branch)
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
        return success
