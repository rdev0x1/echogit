import os
import tempfile
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

    def test_validate_accepts_usable_local_paths(self):
        config = Config.load_from_buffer(
            "[DEFAULT]\nprojects_path=/tmp\ngit_path=/tmp\n"
        )

        self.assertEqual(config.validate(), [])

    def test_validate_reports_missing_projects_path(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={base / 'missing'}\n"
                f"git_path={base}\n"
            )

            issues = config.validate()

        self.assertTrue(any(issue.field == "projects_path" for issue in issues))
        self.assertTrue(any(issue.severity == "error" for issue in issues))

    def test_validate_reports_allowed_path_outside_projects_path(self):
        config = Config.load_from_buffer(
            "[DEFAULT]\n"
            "projects_path=/tmp/echogit-data\n"
            "git_path=/tmp\n"
            "[PEERS]\n"
            "peers=peer1\n"
            "[peer1]\n"
            "allowed_paths=/var/tmp\n"
        )

        issues = config.validate()

        self.assertTrue(
            any(issue.field == "peer1.allowed_paths" for issue in issues)
        )

    def test_load_peers(self):
        peers = self.config._all_peers
        self.assertGreater(len(peers), 0)

    def test_remote_name_marks_peer_as_local(self):
        config = Config.load_from_buffer(
            "[DEFAULT]\n"
            "projects_path=/data\n"
            "git_path=/store\n"
            "remote_name=xps\n"
            "[PEERS]\n"
            "peers=xps,orion\n"
        )

        self.assertTrue(config.is_local_peer("xps"))
        self.assertFalse(config.is_local_peer("orion"))

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
