import tempfile
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.core import EchogitService, ProjectItem


class TestEchogitService(unittest.TestCase):
    def test_list_projects_returns_core_models(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha/.git").mkdir(parents=True)
            (base / "beta/.rsync").mkdir(parents=True)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            projects = service.list_projects()

        self.assertEqual(
            {item.to_dict()["rel"]: item.to_dict()["type"] for item in projects},
            {"alpha": "git", "beta": "rsync"},
        )

    def test_list_remote_projects_returns_core_models_by_peer(self):
        config = Config.load_from_buffer(
            "[DEFAULT]\n"
            "projects_path=/tmp/data\n"
            "git_path=/tmp/store\n"
            "[PEERS]\n"
            "peers=peer1\n"
        )
        service = EchogitService(config)

        with mock.patch.object(
            service,
            "_list_one_remote",
            return_value=[ProjectItem(rel=Path("alpha"), type="git")],
        ):
            remote = service.list_remote_projects(["peer1"])

        self.assertEqual(remote["peer1"][0].to_dict(), {"rel": "alpha", "type": "git"})


if __name__ == "__main__":
    unittest.main()
