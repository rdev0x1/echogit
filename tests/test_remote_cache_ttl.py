import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.folder_node import FolderNode


class TestRemoteCacheTTL(unittest.TestCase):
    def test_remote_cache_ttl(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            cfg_txt = (
                "[DEFAULT]\n"
                f"projects_path={base}\n"
                f"git_path={base}\n"
                "[PEERS]\n"
                "peers=peer1\n"
            )
            config = Config.load_from_buffer(cfg_txt)
            folder = FolderNode(path=base, config=config)

            call_count = {"count": 0}

            def fake_discover(peer, subdir):
                call_count["count"] += 1
                return []

            with mock.patch(
                "echogit.config.is_peer_reachable",
                return_value=True,
            ), mock.patch(
                "echogit.folder_node.discover_remote_projects_under",
                side_effect=fake_discover,
            ), mock.patch(
                "echogit.folder_node.time.monotonic",
                side_effect=[0.0, 30.0, 61.0],
            ):
                folder._load_remote_projects_for_node(on_update=None)
                folder._load_remote_projects_for_node(on_update=None)
                folder._load_remote_projects_for_node(on_update=None)

            self.assertEqual(call_count["count"], 2)

    def test_local_peer_remote_cache_reads_local_store(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            data = base / "data"
            store = base / "store"
            data.mkdir()
            store.mkdir()
            subprocess.run(
                ["git", "init", "--bare", str(store / "missing.git")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={data}\n"
                f"git_path={store}\n"
                "remote_name=xps\n"
                "[PEERS]\n"
                "peers=xps\n"
            )
            folder = FolderNode(path=data, config=config)
            folder.scan()

            with mock.patch(
                "echogit.folder_node.discover_remote_projects_under",
            ) as discover_remote:
                folder._load_remote_projects_for_node(on_update=None)

        discover_remote.assert_not_called()
        self.assertEqual([child.name for child in folder.children], ["missing"])
        self.assertFalse(folder.children[0].state.presence.exists_locally)

    def test_remote_only_local_peer_project_can_clone_from_store(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            data = base / "data"
            store = base / "store"
            data.mkdir()
            store.mkdir()
            subprocess.run(
                ["git", "init", "--bare", str(store / "missing.git")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={data}\n"
                f"git_path={store}\n"
                "remote_name=xps\n"
                "[PEERS]\n"
                "peers=xps\n"
            )
            folder = FolderNode(path=data, config=config)
            folder.scan()
            folder._load_remote_projects_for_node(on_update=None)

            project = folder.children[0]
            self.assertFalse(project.state.presence.exists_locally)
            self.assertEqual(project.state.presence.remote_peers, ["xps"])

            self.assertTrue(project.clone())

            self.assertTrue(project.state.presence.exists_locally)
            self.assertTrue((data / "missing/.git").is_dir())


if __name__ == "__main__":
    unittest.main()
