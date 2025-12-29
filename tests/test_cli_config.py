import configparser
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from echogit.__main__ import _handle_global_config, _handle_project_config
from echogit.config import Config


class TestCliConfig(unittest.TestCase):
    def _with_temp_home(self):
        tmp = tempfile.TemporaryDirectory()
        old_home = os.environ.get("HOME")
        os.environ["HOME"] = tmp.name
        return tmp, old_home

    def _restore_home(self, old_home):
        if old_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = old_home

    def test_global_config_get_set(self):
        tmp, old_home = self._with_temp_home()
        try:
            _handle_global_config(False, "projects_path=/data, ignore_peers_down=true")
            buf = io.StringIO()
            with redirect_stdout(buf):
                _handle_global_config(True, None)
            out = buf.getvalue()
            self.assertIn("Data Path: /data", out)
            self.assertIn("Ignore peers down: True", out)
        finally:
            tmp.cleanup()
            self._restore_home(old_home)

    def test_project_config_get_set(self):
        tmp, old_home = self._with_temp_home()
        try:
            base = Path(tmp.name)
            cfg_path = base / ".config/echogit/config.ini"
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg = configparser.ConfigParser()
            cfg["DEFAULT"] = {
                "projects_path": str(base),
                "git_path": str(base),
            }
            cfg["AUTOCOMMIT"] = {"projects": "proj"}
            with cfg_path.open("w", encoding="utf-8") as f:
                cfg.write(f)

            config = Config.load_from_buffer(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n"
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                _handle_project_config(
                    config, str(base / "proj"), do_get=True, set_values=None
                )
            self.assertIn("Auto commit: True", buf.getvalue())

            _handle_project_config(
                config,
                str(base / "proj"),
                do_get=False,
                set_values="autoCommit:false",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                _handle_project_config(
                    config, str(base / "proj"), do_get=True, set_values=None
                )
            self.assertIn("Auto commit: False", buf.getvalue())
        finally:
            tmp.cleanup()
            self._restore_home(old_home)


if __name__ == "__main__":
    unittest.main()
