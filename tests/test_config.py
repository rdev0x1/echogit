import os
import unittest
from pathlib import Path

from echogit.config import Config


class TestConfig(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        test_path = os.path.dirname(os.path.realpath(__file__))
        test_path = os.path.join(test_path, "../test_dir/config/config_test.ini")
        cls.config = Config.load_from_file(Path(test_path))

    def test_project_path(self):
        self.assertIsNotNone(self.config.projects_path)

    def test_git_path(self):
        self.assertIsNotNone(self.config.git_path)

    def test_load_peers(self):
        peers = self.config._all_peers
        self.assertGreater(len(peers), 0)


if __name__ == "__main__":
    unittest.main()
