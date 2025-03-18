import os
import unittest
from echogit.sync_folder import SyncFolder
from echogit.config import Config


class TestSyncFolder(unittest.TestCase):

    def setUp(self):
        test_path = os.path.dirname(os.path.realpath(__file__))
        test_path = os.path.join(
            test_path, "../test_dir/config/config_test.ini")
        self.config = Config(test_path)
        self.folder = SyncFolder(path=self.config.projects_path,
                                 config=self.config)

    def test_is_folder(self):
        self.assertTrue(self.folder.is_folder())

    def test_scan(self):
        self.folder.scan()

    def test_sync(self):
        # Sync should run without errors
        self.folder.sync()


if __name__ == "__main__":
    unittest.main()
