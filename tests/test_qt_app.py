import unittest
from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile

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
            (base / "notes/work/.git").mkdir(parents=True)
            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            service = EchogitService(config)

            app = qt_app.QtWidgets.QApplication.instance()
            if app is None:
                app = qt_app.QtWidgets.QApplication([])
            window = qt_app.MainWindow(service)

        self.assertEqual(window.project_tree.topLevelItemCount(), 1)
        self.assertIn("2 projects", window.summary_label.text())

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

        item = window.project_tree.topLevelItem(0)
        node = item.data(0, qt_app.NODE_ROLE)
        node.log("manual log line")
        window.project_tree.setCurrentItem(item)
        window._show_node_details(node)

        self.assertIn("manual log line", window.log.toPlainText())


if __name__ == "__main__":
    unittest.main()
