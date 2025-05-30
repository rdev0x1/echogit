"""
Utility functions for SSH commands and safe subprocess execution.
"""

import logging
import subprocess


def run_ssh_command(peer_host: str, command: str) -> tuple[bool, str]:
    """
    Run a command on a remote host via SSH.

    :param peer_host: SSH host identifier
    :param command: command string to run remotely
    :returns: (success, combined_output)
    """
    ssh_command = ["ssh", peer_host, command]
    return safe_run_command(ssh_command)


def is_peer_reachable(peer: str, timeout: int = 2) -> bool:
    """
    Return True if ssh is working in under `timeout` seconds.
    """
    timeout_opt = f"ConnectTimeout={timeout}"
    cmd = ["ssh", "-o", "BatchMode=yes", "-o", timeout_opt, peer, "true"]

    success, _ = safe_run_command(cmd)
    return success


def safe_run_command(cmd: list[str], cwd: str | None = None) -> tuple[bool, str]:
    """
    Run a subprocess with given command list, capturing output.

    :param cmd: list of command arguments
    :param cwd: working directory or None
    :returns: (success, stdout or combined error)
    """

    out = f"command: {' '.join(cmd)}"
    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, check=True
        )
        out += f"\nsuccess\nSTDOUT:\n{result.stdout}"
        logging.info(out)
        # in case of success, return stdout as it as it could be parsed by the caller
        return True, result.stdout

    except subprocess.CalledProcessError as e:
        out += f"\nfailed\nSTDOUT:\n{e.stdout}\nSTDERR:\n{e.stderr}\n"
        logging.error(out)
        return False, out
