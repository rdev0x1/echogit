import unittest
from contextlib import redirect_stderr
import io
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from echogit.gui import qt_app
from echogit.core import ProjectItem


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

    def test_main_window_uses_project_tree(self):
        if qt_app.QtWidgets is None:
            self.skipTest("PySide6 is not installed")

        class FakeService:
            def list_projects(self):
                return [
                    ProjectItem(rel=Path("music/album"), type="rsync"),
                    ProjectItem(rel=Path("notes/work"), type="git"),
                ]

        app = qt_app.QtWidgets.QApplication.instance()
        if app is None:
            app = qt_app.QtWidgets.QApplication([])
        window = qt_app.MainWindow(FakeService())

        self.assertEqual(window.project_tree.topLevelItemCount(), 2)
        self.assertIn("2 projects", window.summary_label.text())


if __name__ == "__main__":
    unittest.main()
