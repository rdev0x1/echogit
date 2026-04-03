import tempfile
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.sync.branch_node import BranchNode
from echogit.sync.git_peer_node import GitPeerNode
from echogit.sync.git_sync import GitProjectNode


class TestGitPeerNode(unittest.TestCase):
    def test_fetch_remote_branches_reads_remote_refs(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "repo"
            project_path.mkdir()
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            project = GitProjectNode(path=project_path, config=config)
            peer = GitPeerNode(path=project_path, peer_name="peer1", parent=project)

            with mock.patch(
                "echogit.sync.git_peer_node.safe_run_command",
                return_value=(
                    True,
                    "\n".join(
                        [
                            "refs/remotes/peer1/HEAD",
                            "refs/remotes/peer1/main",
                            "refs/remotes/peer1/feature/photos",
                            "refs/heads/local-only",
                        ]
                    ),
                ),
            ) as run_cmd:
                branches = peer._fetch_remote_branches()

            self.assertEqual(branches, ["feature/photos", "main"])
            run_cmd.assert_called_once_with(
                [
                    "git",
                    "-C",
                    str(project_path),
                    "for-each-ref",
                    "--format=%(refname)",
                    "refs/remotes/peer1",
                ]
            )

    def test_sync_loads_fetched_remote_branches_before_child_sync(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "repo"
            project_path.mkdir()
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            remote_config = Config.load_from_buffer(
                "[DEFAULT]\nprojects_path=/remote/data\ngit_path=/remote/store\n"
            )
            project = GitProjectNode(path=project_path, config=config)
            peer = GitPeerNode(path=project_path, peer_name="peer1", parent=project)

            desired_url = "peer1:/remote/store/repo.git"

            def fake_run(cmd, cwd=None):
                _ = cwd
                if cmd == [
                    "git",
                    "-C",
                    str(project_path),
                    "remote",
                    "get-url",
                    "peer1",
                ]:
                    return True, desired_url
                if cmd == ["git", "-C", str(project_path), "fetch", "peer1"]:
                    return True, ""
                if cmd == [
                    "git",
                    "-C",
                    str(project_path),
                    "for-each-ref",
                    "--format=%(refname)",
                    "refs/remotes/peer1",
                ]:
                    return True, "refs/remotes/peer1/main\n"
                raise AssertionError(f"unexpected command: {cmd!r}")

            with mock.patch(
                "echogit.sync.git_peer_node.Config.get_config_peer",
                return_value=remote_config,
            ), mock.patch(
                "echogit.sync.git_peer_node._is_local_peer",
                return_value=False,
            ), mock.patch(
                "echogit.sync.git_peer_node.safe_run_command",
                side_effect=fake_run,
            ), mock.patch.object(
                BranchNode,
                "sync",
                return_value=True,
            ) as branch_sync:
                self.assertTrue(peer.sync())

            self.assertEqual([child.name for child in peer.children], ["main"])
            branch_sync.assert_called_once()

    def test_clone_command_uses_scp_style_remote_location(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "repo"
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            project = GitProjectNode(path=project_path, config=config)
            peer = GitPeerNode(path=project_path, peer_name="peer1", parent=project)

            with mock.patch(
                "echogit.sync.git_peer_node._is_local_peer",
                return_value=False,
            ):
                cmd = peer.get_clone_command(Path("repo"), Path("~/store"))

        self.assertEqual(
            cmd,
            [
                "git",
                "clone",
                "peer1:~/store/repo.git",
                str(project_path),
            ],
        )


if __name__ == "__main__":
    unittest.main()
