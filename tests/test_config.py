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

    def test_allowed_paths_are_relative_to_expanded_projects_path(self):
        home = Path("/tmp/echogit-home")
        config = Config.load_from_buffer(
            "[DEFAULT]\n"
            "projects_path=~/data\n"
            "git_path=~/store\n"
            "[PEERS]\n"
            "peers=peer1\n"
            "[peer1]\n"
            "allowed_paths=music, photos\n",
            home_dir=home,
        )

        self.assertTrue(
            config.is_path_allowed("peer1", home / "data" / "music" / "album")
        )
        self.assertTrue(
            config.is_path_allowed("peer1", home / "data" / "photos" / "2026")
        )
        self.assertFalse(
            config.is_path_allowed("peer1", home / "data" / "private")
        )

    def test_allowed_paths_expand_remote_home_paths(self):
        home = Path("/home/remote")
        config = Config.load_from_buffer(
            "[DEFAULT]\n"
            "projects_path=~/data\n"
            "git_path=~/store\n"
            "[PEERS]\n"
            "peers=peer1\n"
            "[peer1]\n"
            "allowed_paths=~/shared\n",
            home_dir=home,
        )

        self.assertTrue(
            config.is_path_allowed("peer1", home / "shared" / "project")
        )
        self.assertFalse(
            config.is_path_allowed("peer1", home / "data" / "shared")
        )


if __name__ == "__main__":
    unittest.main()
