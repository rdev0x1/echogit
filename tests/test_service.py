import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from echogit.config import Config
from echogit.core import EchogitService, ProjectItem
from echogit.folder_node import FolderNode


class TestEchogitService(unittest.TestCase):
    def test_list_projects_returns_core_models(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha").mkdir()
            subprocess.run(
                ["git", "init", str(base / "alpha")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
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

    def test_list_remote_projects_uses_local_store_for_local_peer(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            store = base / "store"
            store.mkdir()
            subprocess.run(
                ["git", "init", "--bare", str(store / "alpha.git")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={base / 'data'}\n"
                f"git_path={store}\n"
                "remote_name=xps\n"
                "[PEERS]\n"
                "peers=xps\n"
            )
            service = EchogitService(config)

            with mock.patch(
                "echogit.core.service.discover_remote_projects",
            ) as discover_remote:
                remote = service.list_remote_projects(["xps"])

        discover_remote.assert_not_called()
        self.assertEqual(remote["xps"][0].to_dict(), {"rel": "alpha", "type": "git"})

    def test_build_tree_ignores_invalid_root_git_marker(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / ".git").mkdir()
            (base / "alpha").mkdir()
            subprocess.run(
                ["git", "init", str(base / "alpha")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            service = EchogitService(config)

            root = service.build_tree()
            projects = service.list_projects()

        self.assertIsInstance(root, FolderNode)
        self.assertEqual([child.name for child in root.children], ["alpha"])
        self.assertEqual([project.rel for project in projects], [Path("alpha")])

    def test_smoke_counts_local_tree_without_syncing(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha").mkdir()
            subprocess.run(
                ["git", "init", str(base / "alpha")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            (base / "beta/.rsync").mkdir(parents=True)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base / 'store'}\n"
            )
            service = EchogitService(config)

            report = service.smoke()

        self.assertEqual(report.projects, 2)
        self.assertEqual(report.git_projects, 1)
        self.assertEqual(report.rsync_projects, 1)
        self.assertEqual(report.errors, 0)
        self.assertEqual(report.to_dict()["projects"], 2)


if __name__ == "__main__":
    unittest.main()
