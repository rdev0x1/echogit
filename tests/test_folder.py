import os
import unittest
from pathlib import Path

from echogit.folder_node import FolderNode
from echogit.config import Config


class TestSyncFolder(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        test_path = os.path.dirname(os.path.realpath(__file__))
        test_path = os.path.join(test_path, "../test_dir/config/config_test.ini")
        cls.config = Config.load_from_file(Path(test_path))

    def setUp(self):
        self.folder = FolderNode(path=self.config.projects_path, config=self.config)

    def test_is_folder(self):
        self.assertTrue(self.folder.is_folder)

    def test_scan(self):
        self.folder.scan()

    def test_sync(self):
        # Sync should run without errors
        self.folder.sync()


if __name__ == "__main__":
    unittest.main()
