import os
import unittest
from pathlib import Path

from echogit.config import Config
from echogit.node import Node


class DummyNode(Node):
    def __init__(self, path: Path, *, config: Config, succeed: bool = True):
        super().__init__(path=path, config=config)
        self._succeed = succeed

    def sync(self, on_progress=None) -> bool:
        if self._succeed:
            return super().sync(on_progress=on_progress)
        self.state.sync.state = "error"
        if self.state.sync.current_gen is not None:
            self.mark_synced(self.state.sync.current_gen, False)
        if on_progress:
            on_progress(self, False)
        return False


class TestSyncState(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        test_path = os.path.dirname(os.path.realpath(__file__))
        test_path = os.path.join(test_path, "../test_dir/config/config_test.ini")
        cls.config = Config.load_from_file(Path(test_path))

    def test_sync_state_unknown_initial(self):
        node = DummyNode(self.config.projects_path / "dummy", config=self.config)
        self.assertEqual(node.sync_state(), "unknown")

    def test_sync_state_ok_after_sync(self):
        node = DummyNode(self.config.projects_path / "dummy", config=self.config)
        gen = node.begin_sync()
        ok = node.sync()
        self.assertTrue(ok)
        self.assertEqual(node.sync_state(), "ok")
        self.assertTrue(node.is_synced(gen))

    def test_sync_state_error_propagates(self):
        parent = DummyNode(self.config.projects_path / "parent", config=self.config)
        child = DummyNode(
            self.config.projects_path / "child", config=self.config, succeed=False
        )
        parent.add_child(child)
        gen = parent.begin_sync()
        ok = parent.sync()
        self.assertFalse(ok)
        self.assertEqual(parent.sync_state(), "error")
        self.assertTrue(parent.is_synced(gen))
        self.assertEqual(child.sync_state(), "error")

    def test_skip_sync_records_category(self):
        node = DummyNode(self.config.projects_path / "dummy", config=self.config)
        gen = node.begin_sync()

        self.assertTrue(node.skip_sync(reason="peer_down"))

        self.assertEqual(node.sync_state(), "skipped")
        self.assertEqual(node.state.sync.reason, "peer_down")
        self.assertTrue(node.is_synced(gen))


if __name__ == "__main__":
    unittest.main()
