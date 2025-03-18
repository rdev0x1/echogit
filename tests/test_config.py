import os
import unittest
from echogit.config import Config


class TestConfig(unittest.TestCase):

    def setUp(self):
        test_path = os.path.dirname(os.path.realpath(__file__))
        test_path = os.path.join(
            test_path, "../test_dir/config/config_test.ini")
        self.config = Config(test_path)

    def test_project_path(self):
        self.assertIsNotNone(self.config.projects_path)

    def test_git_path(self):
        self.assertIsNotNone(self.config.git_path)

    def test_load_peers(self):
        peers = self.config.get_peers()
        self.assertGreater(len(peers), 0)


if __name__ == "__main__":
    unittest.main()
