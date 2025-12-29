import tempfile
import unittest
from pathlib import Path

from echogit.config import Config
from echogit.folder_node import FolderNode


class TestRescanKeepsChildren(unittest.TestCase):
    def test_scan_twice_keeps_children(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha").mkdir()
            (base / "beta").mkdir()

            cfg_txt = f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            config = Config.load_from_buffer(cfg_txt)
            folder = FolderNode(path=base, config=config)
            folder.scan()
            first = {child.name for child in folder.children}
            self.assertEqual(first, {"alpha", "beta"})

            folder.scan()
            second = {child.name for child in folder.children}
            self.assertEqual(second, {"alpha", "beta"})


if __name__ == "__main__":
    unittest.main()
