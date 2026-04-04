import unittest
from contextlib import redirect_stderr
import io

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


if __name__ == "__main__":
    unittest.main()
