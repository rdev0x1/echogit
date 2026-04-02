import tempfile
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.sync.branch_node import BranchNode
from echogit.sync.git_peer_node import GitPeerNode
from echogit.sync.git_sync import GitProjectNode


class TestBranchNode(unittest.TestCase):
    def _branch_node(self, base: Path, branch_name: str = "feature") -> BranchNode:
        project_path = base / "repo"
        project_path.mkdir(exist_ok=True)
        config = Config.load_from_buffer(
            "[DEFAULT]\n"
            f"projects_path={base}\n"
            f"git_path={base / 'store'}\n"
        )
        project = GitProjectNode(path=project_path, config=config)
        peer = GitPeerNode(path=project_path, peer_name="localhost", parent=project)
        return BranchNode(path=project_path, branch_name=branch_name, parent=peer)

    def test_remote_branch_exists_checks_local_peer_remote_refs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            branch = self._branch_node(base, branch_name="main")

            with mock.patch(
                "echogit.sync.branch_node.safe_run_command",
                return_value=(True, ""),
            ) as run_cmd:
                self.assertFalse(
                    branch._remote_branch_exists(str(branch.path), "localhost", "main")
                )

            run_cmd.assert_called_once_with(
                [
                    "git",
                    "-C",
                    str(branch.path),
                    "ls-remote",
                    "--heads",
                    "localhost",
                    "main",
                ],
                cwd=str(branch.path),
            )

    def test_auto_commit_checks_out_target_branch_when_refs_match(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "repo"
            project_path.mkdir()
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={base}\n"
                f"git_path={base / 'store'}\n"
                "[AUTOCOMMIT]\n"
                "projects=repo\n"
            )
            project = GitProjectNode(path=project_path, config=config)
            peer = GitPeerNode(path=project_path, peer_name="peer1", parent=project)
            branch = BranchNode(path=project_path, branch_name="feature", parent=peer)

            with mock.patch.object(
                branch,
                "_current_branch",
                side_effect=["main", "main"],
            ), mock.patch.object(
                branch,
                "_remote_branch_exists",
                return_value=True,
            ), mock.patch.object(
                branch,
                "_fetch_remote_branch",
                return_value=True,
            ), mock.patch.object(
                branch,
                "_refs_match",
                return_value=True,
            ), mock.patch.object(
                branch,
                "_checkout_or_create",
                return_value=True,
            ) as checkout, mock.patch.object(
                branch,
                "_auto_commit",
                return_value=True,
            ) as auto_commit, mock.patch.object(
                branch,
                "_push_branch",
                return_value=True,
            ):
                self.assertTrue(branch.sync())

            checkout.assert_called_once_with(str(project_path), "peer1", "feature")
            auto_commit.assert_called_once_with(str(project_path), "main", None)


if __name__ == "__main__":
    unittest.main()
