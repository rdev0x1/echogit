import tempfile
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


if __name__ == "__main__":
    unittest.main()
