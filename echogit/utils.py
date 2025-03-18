import logging
import subprocess


def safe_run_command(cmd: list[str], cwd: str | None = None) -> tuple[bool, str]:

    out = f"command: {' '.join(cmd)}"

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=True
        )
        out += f"\nsuccess\nSTDOUT:\n{result.stdout}"
        logging.info(out)
        return True, out

    except subprocess.CalledProcessError as e:
        out += "\nfailed\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}\n"
        logging.error(out)
        return False, out
