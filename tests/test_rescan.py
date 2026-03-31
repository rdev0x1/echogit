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

    def test_scan_context_isolated_between_roots(self):
        with tempfile.TemporaryDirectory() as first_dir:
            with tempfile.TemporaryDirectory() as second_dir:
                first_base = Path(first_dir)
                second_base = Path(second_dir)
                (first_base / "alpha").mkdir()
                (second_base / "alpha").mkdir()

                first_config = Config.load_from_buffer(
                    f"[DEFAULT]\nprojects_path={first_base}\ngit_path={first_base}\n"
                )
                second_config = Config.load_from_buffer(
                    f"[DEFAULT]\nprojects_path={second_base}\ngit_path={second_base}\n"
                )

                first_folder = FolderNode(path=first_base, config=first_config)
                first_folder.scan()

                second_folder = FolderNode(path=second_base, config=second_config)
                second_folder.scan()

                self.assertEqual(first_folder.children[0].path, first_base / "alpha")
                self.assertEqual(
                    second_folder.children[0].path,
                    second_base / "alpha",
                )
                self.assertIsNot(first_folder.children[0], second_folder.children[0])


if __name__ == "__main__":
    unittest.main()
