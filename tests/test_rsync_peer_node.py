import tempfile
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.sync.rsync_peer_node import RsyncPeerNode
from echogit.sync.rsync_sync import RsyncProjectNode


class TestRsyncPeerNode(unittest.TestCase):
    def test_sync_skips_unreachable_peer_before_rsync_commands(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "media"
            project_path.mkdir()
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={base}\n"
                f"git_path={base / 'store'}\n"
                "ignore_peers_down=true\n"
            )
            project = RsyncProjectNode(path=project_path, config=config)
            peer = RsyncPeerNode(
                path=project_path,
                peer_name="peer1",
                parent=project,
            )

            with mock.patch(
                "echogit.sync.rsync_peer_node.is_peer_reachable",
                return_value=False,
            ), mock.patch(
                "echogit.sync.rsync_peer_node.Config.get_config_peer",
            ) as get_config, mock.patch(
                "echogit.sync.rsync_peer_node.safe_run_command",
            ) as run_cmd:
                self.assertTrue(peer.sync())

            get_config.assert_not_called()
            run_cmd.assert_not_called()
            self.assertEqual(peer.sync_state(), "unknown")

    def test_sync_targets_peer_rsync_store(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "media"
            project_path.mkdir()
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            remote_config = Config.load_from_buffer(
                "[DEFAULT]\nprojects_path=/remote/data\ngit_path=/remote/store\n"
            )
            project = RsyncProjectNode(path=project_path, config=config)
            peer = RsyncPeerNode(
                path=project_path,
                peer_name="peer1",
                parent=project,
            )

            with mock.patch(
                "echogit.sync.rsync_peer_node.Config.get_config_peer",
                return_value=remote_config,
            ), mock.patch(
                "echogit.sync.rsync_peer_node._is_local_peer",
                return_value=False,
            ), mock.patch(
                "echogit.sync.rsync_peer_node.run_ssh_command",
                return_value=(True, ""),
            ) as run_ssh, mock.patch(
                "echogit.sync.rsync_peer_node.safe_run_command",
                return_value=(True, ""),
            ) as run_cmd:
                self.assertTrue(peer.sync())

            run_ssh.assert_called_once_with(
                "peer1",
                "mkdir -p /remote/store/media.rsync",
            )
            run_cmd.assert_called_once_with(
                [
                    "rsync",
                    "-aur",
                    "--exclude",
                    ".echogit/",
                    "--exclude",
                    ".rsync/",
                    str(project_path) + "/",
                    "peer1:/remote/store/media.rsync/",
                ]
            )

    def test_clone_command_uses_rsync_source_not_remote_shell_option(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "media"
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            project = RsyncProjectNode(path=project_path, config=config)
            peer = RsyncPeerNode(
                path=project_path,
                peer_name="peer1",
                parent=project,
            )

            with mock.patch(
                "echogit.sync.rsync_peer_node._is_local_peer",
                return_value=False,
            ):
                cmd = peer.get_clone_command(Path("media"), Path("/remote/store"))

        self.assertEqual(
            cmd,
            [
                "rsync",
                "-aur",
                "peer1:/remote/store/media.rsync/",
                str(project_path) + "/",
            ],
        )
        self.assertNotIn("-e", cmd)


if __name__ == "__main__":
    unittest.main()
