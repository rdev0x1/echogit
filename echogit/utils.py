"""
Utility functions for SSH commands and safe subprocess execution.
"""

import logging
import shlex
import socket
import subprocess
from typing import Set


def _is_local_peer(peer_host: str) -> bool:
    if peer_host in {"localhost", "127.0.0.1", "::1"}:
        return True
    host = socket.gethostname()
    fqdn = socket.getfqdn()
    if peer_host in {host, fqdn}:
        return True
    peer_ips = _resolve_ips(peer_host)
    if not peer_ips:
        return False
    local_ips = _resolve_ips(host)
    return bool(peer_ips & local_ips)


def _resolve_ips(host: str) -> Set[str]:
    try:
        return {addr[0] for addr in socket.getaddrinfo(host, None)}
    except socket.gaierror:
        return set()


def run_ssh_command(
    peer_host: str,
    command: str,
    timeout: int | None = None,
    batch_mode: bool = False,
) -> tuple[bool, str]:
    """
    Run a command on a remote host via SSH.

    :param peer_host: SSH host identifier
    :param command: command string to run remotely
    :returns: (success, combined_output)
    """
    if _is_local_peer(peer_host):
        return safe_run_command(["bash", "-lc", command])
    ssh_command = ["ssh"]
    if batch_mode:
        ssh_command.extend(["-o", "BatchMode=yes"])
    if timeout is not None:
        ssh_command.extend(["-o", f"ConnectTimeout={timeout}"])
    ssh_command.extend([peer_host, command])
    return safe_run_command(ssh_command)


def is_peer_reachable(peer: str, timeout: int = 2) -> bool:
    """
    Return True if ssh is working in under `timeout` seconds.
    """
    if _is_local_peer(peer):
        return True
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

    cmd_str = " ".join(shlex.quote(part) for part in cmd)
    out = f"command: {cmd_str}"
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
    except FileNotFoundError as e:
        out += f"\nfailed\nSTDERR:\n{e}\n"
        logging.error(out)
        return False, out
