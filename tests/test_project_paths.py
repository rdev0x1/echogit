import tempfile
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.sync.git_peer_node import GitPeerNode
from echogit.sync.git_sync import GitProjectNode
from echogit.sync.rsync_peer_node import RsyncPeerNode
from echogit.sync.rsync_sync import RsyncProjectNode


class TestProjectPaths(unittest.TestCase):
    def test_git_store_path_appends_suffix_to_project_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "notes.v1"
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            node = GitProjectNode(path=project_path, config=config)

            self.assertEqual(node.git_path, base / "store" / "notes.v1.git")

    def test_git_peer_path_appends_suffix_to_project_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "notes.v1"
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            remote_config = Config.load_from_buffer(
                "[DEFAULT]\nprojects_path=/remote/data\ngit_path=/remote/store\n"
            )
            project = GitProjectNode(path=project_path, config=config)
            peer = GitPeerNode(path=project_path, peer_name="peer1", parent=project)

            with mock.patch(
                "echogit.sync.git_peer_node.Config.get_config_peer",
                return_value=remote_config,
            ):
                self.assertEqual(
                    peer.git_path,
                    Path("/remote/store/notes.v1.git"),
                )

    def test_rsync_store_path_appends_suffix_to_project_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "photos.2026"
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            node = RsyncProjectNode(path=project_path, config=config)

            self.assertEqual(node.rsync_path, base / "store" / "photos.2026.rsync")

    def test_rsync_peer_path_appends_suffix_to_project_name(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            project_path = base / "photos.2026"
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            remote_config = Config.load_from_buffer(
                "[DEFAULT]\nprojects_path=/remote/data\ngit_path=/remote/store\n"
            )
            project = RsyncProjectNode(path=project_path, config=config)
            peer = RsyncPeerNode(path=project_path, peer_name="peer1", parent=project)

            with mock.patch(
                "echogit.sync.rsync_peer_node.Config.get_config_peer",
                return_value=remote_config,
            ):
                self.assertEqual(
                    peer.rsync_path,
                    Path("/remote/store/photos.2026.rsync"),
                )


if __name__ == "__main__":
    unittest.main()
