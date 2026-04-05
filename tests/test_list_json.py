import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from echogit.__main__ import main


class TestListJson(unittest.TestCase):
    def test_list_json_output(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "alpha").mkdir()
            (base / "beta").mkdir()
            subprocess.run(
                ["git", "init", str(base / "alpha")],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            (base / "beta/.rsync").mkdir()

            cfg_path = base / ".config/echogit/config.ini"
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(
                f"[DEFAULT]\nprojects_path={base}\ngit_path={base}\n",
                encoding="utf-8",
            )

            old_argv = os.sys.argv[:]
            try:
                os.sys.argv = [
                    "echogit",
                    "list",
                    "--json",
                ]
                old_home = os.environ.get("HOME")
                os.environ["HOME"] = str(base)
                out = _capture_stdout(main)
            finally:
                os.sys.argv = old_argv
                if old_home is None:
                    os.environ.pop("HOME", None)
                else:
                    os.environ["HOME"] = old_home

            data = json.loads(out)
            rels = {item["rel"] for item in data}
            self.assertIn("alpha", rels)
            self.assertIn("beta", rels)


def _capture_stdout(func):
    import io
    from contextlib import redirect_stdout

    buf = io.StringIO()
    with redirect_stdout(buf):
        func()
    return buf.getvalue()


if __name__ == "__main__":
    unittest.main()
