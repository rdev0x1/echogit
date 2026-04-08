import unittest
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from echogit.config import Config
from echogit.core import EchogitService
from echogit.gui import qt_app


class TestQtApp(unittest.TestCase):
    def test_missing_dependency_message_mentions_extra(self):
        self.assertIn(".[qt]", qt_app.missing_dependency_message())

    def test_main_returns_install_error_when_qt_is_missing(self):
        if qt_app.QtWidgets is not None:
            self.skipTest("PySide6 is installed")

        stderr = io.StringIO()
        with redirect_stderr(stderr):
            code = qt_app.main()

        self.assertEqual(code, 2)
        self.assertIn("PySide6", stderr.getvalue())

    def test_main_window_uses_node_tree(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "music/album/.rsync").mkdir(parents=True)
            (base / "notes/work").mkdir(parents=True)
            subprocess.run(
                ["git", "init", str(base / "notes/work")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

        self.assertEqual(window.project_tree.topLevelItemCount(), 1)
        self.assertIn("2 projects", window.summary_label.text())
        self.assertEqual(window.progress_bar.value(), 0)

    def test_config_action_counts_validation_warnings(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            data = base / "data"
            data.mkdir()
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={data}\n"
                f"git_path={base / 'missing-store'}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

        self.assertEqual(window.config_action.text(), "Config (1)")

    def test_config_dialog_lists_validation_issues(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={base / 'missing-data'}\n"
                f"git_path={base}\n"
            )

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            dialog = qt_app.ConfigDialog(config)

        item = dialog.issue_tree.topLevelItem(0)
        self.assertEqual(item.text(0), "ERROR")
        self.assertEqual(item.text(1), "projects_path")

    def test_main_window_shows_selected_node_log(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha/.rsync").mkdir(parents=True)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

        item = window.project_tree.topLevelItem(0)
        node = item.data(0, qt_app.NODE_ROLE)
        node.log("manual log line")
        window.project_tree.setCurrentItem(item)
        window._show_node_details(node)

        self.assertIn("manual log line", window.log.toPlainText())

    def test_sync_progress_bar_tracks_node_progress(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha/.rsync").mkdir(parents=True)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

        total = qt_app._sync_progress_total(window._root)
        project = window._root.children[0]
        window._on_sync_prepared(total)
        window._on_sync_progress(window._root, True)
        window._on_sync_progress(project, True)

        self.assertEqual(total, 2)
        self.assertEqual(window.progress_bar.maximum(), 2)
        self.assertEqual(window.progress_bar.value(), 2)

    def test_skipped_node_status_is_distinct(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            node = qt_app.FolderNode(path=base, config=config)

        node.skip_sync(reason="peer_down")

        self.assertEqual(qt_app._node_status_text(node), "SKIP")
        self.assertIn("peer_down", node.state.sync.reason)

    def test_busy_cursor_is_scoped(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

        try:
            window._set_wait_cursor(True)
            self.assertIsNotNone(app.overrideCursor())
            window._set_wait_cursor(False)
            self.assertIsNone(app.overrideCursor())
        finally:
            while app.overrideCursor() is not None:
                app.restoreOverrideCursor()

    def test_expanding_node_loads_children_in_background(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha").mkdir()
            subprocess.run(
                ["git", "init", str(base / "alpha")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            config = Config.load_from_buffer(
                "[DEFAULT]\n"
                f"projects_path={base}\n"
                f"git_path={base / 'store'}\n"
                "remote_name=xps\n"
                "[PEERS]\n"
                "peers=xps\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

            project_item = window.project_tree.topLevelItem(0).child(0)
            peer_item = project_item.child(0)
            peer_node = peer_item.data(0, qt_app.NODE_ROLE)

            self.assertFalse(peer_node.is_scanned())
            window._on_item_expanded(peer_item)
            self.assertIsNotNone(window._load_thread)
            _wait_for_idle(window)

        self.assertTrue(peer_node.is_scanned())

    def test_node_actions_copy_path_and_focus_log(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

        item = window.project_tree.topLevelItem(0)
        window.project_tree.setCurrentItem(item)
        window.copy_selected_path()
        window.focus_selected_log()

        self.assertEqual(app.clipboard().text(), str(window._root.path))
        self.assertTrue(window.copy_path_action.isEnabled())
        self.assertTrue(window.show_log_action.isEnabled())

    def test_refresh_selected_node_uses_background_loader(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

            window.project_tree.setCurrentItem(window.project_tree.topLevelItem(0))
            window.refresh_selected_node()
            self.assertIsNotNone(window._load_thread)
            _wait_for_idle(window)

        self.assertIsNone(window._load_thread)

    def test_clone_action_runs_in_background_for_remote_node(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha/.rsync").mkdir(parents=True)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)
            _wait_for_idle(window)

            item = window.project_tree.topLevelItem(0).child(0)
            node = item.data(0, qt_app.NODE_ROLE)
            node.state.presence.exists_locally = False
            window.project_tree.setCurrentItem(item)
            window._update_action_state()

            def clone_ok():
                node.state.presence.exists_locally = True
                return True

            with mock.patch.object(node, "clone", side_effect=clone_ok) as clone:
                window.clone_selected_node()
                self.assertIsNotNone(window._clone_thread)
                _wait_for_idle(window)

        clone.assert_called_once()
        self.assertIsNone(window._clone_thread)
        self.assertFalse(window.clone_node_action.isEnabled())


def _wait_for_idle(window, timeout: float = 5.0) -> None:
    app = qt_app.QtWidgets.QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents(qt_app.QtCore.QEventLoop.AllEvents, 50)
        if not window._is_busy():
            if window._root is None:
                raise AssertionError(window.activity_label.text())
            return
        time.sleep(0.01)
    raise AssertionError(
        f"Qt background work did not finish: {window.statusBar().currentMessage()}"
    )


if __name__ == "__main__":
    unittest.main()
