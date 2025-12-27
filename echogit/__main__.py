"""
entry point for Echogit, a program that help you sync your projects using git or rsync.
"""

import argparse
import logging
import sys
from pathlib import Path

from echogit.config import Config
from echogit.discovery import discover_local_projects, discover_remote_projects
from echogit.node_factory import from_path
from echogit.tui import run_ui


def main():
    """
    Echogit entry point
    """
    parser = argparse.ArgumentParser(description="Echogit CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List local projects")
    subparsers.add_parser("list-remote", help="List remote projects")

    sync_parser = subparsers.add_parser("sync", help="Sync local projects")
    sync_parser.add_argument("path", nargs="?", default=None)
    sync_parser.add_argument(
        "--verbose",
        "-v",
        type=int,
        choices=[0, 1, 2],
        default=1,
        help="verbosity level: 0=critical, 1=error, 2=info",
    )
    sync_parser.add_argument(
        "--progress",
        action="store_true",
        help="print each project as it syncs",
    )
    sync_parser.add_argument(
        "--status",
        action="store_true",
        help="include dirty status in progress output",
    )

    tui_parser = subparsers.add_parser("tui", help="Launch TUI interface")
    tui_parser.add_argument("path", nargs="?", default=None)

    args = parser.parse_args()
    config = Config.load_from_file()

    if args.command != "sync" or args.verbose == 0:
        logging.basicConfig(level=logging.CRITICAL)
    elif args.verbose == 1:
        logging.basicConfig(level=logging.ERROR)
    elif args.verbose >= 2:
        logging.basicConfig(level=logging.INFO)
    _enable_color_logging()

    if args.command == "list":
        for proj in discover_local_projects(config.projects_path):
            print(proj)

    elif args.command == "list-remote":
        for peer_name in config.peers:
            print(f"Projects on peer '{peer_name}':")
            for proj in discover_remote_projects(peer_name):
                print(f"  - {proj}")

    elif args.command == "sync":
        path = Path(args.path or config.projects_path)
        root_node = from_path(path, config=config)
        root_node.scan()
        if args.progress:
            from echogit.sync.project_node import ProjectNode

            def on_progress(node, ok):
                if isinstance(node, ProjectNode):
                    if args.status and node.is_dirty():
                        status = "DIRTY"
                    else:
                        status = "OK" if ok else "ERR"
                    line = f"{status} {node.relative_path}"
                    print(_color_status(status, line))

            success = root_node.sync(on_progress=on_progress)
        else:
            success = root_node.sync()
        if success:
            print("Sync OK")
        else:
            print("Sync failed")
            sys.exit(1)

    elif args.command == "tui":
        path = Path(args.path or config.projects_path)
        run_ui(path, config)


def _color_status(status: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    parts = text.split(" ", 1)
    if len(parts) != 2:
        return text
    colors = {
        "OK": "\x1b[32m",
        "ERR": "\x1b[31m",
        "DIRTY": "\x1b[33m",
    }
    color = colors.get(status)
    if not color:
        return text
    return f"{color}{parts[0]}\x1b[0m {parts[1]}"


def _enable_color_logging() -> None:
    if not sys.stderr.isatty():
        return
    root = logging.getLogger()
    if not root.handlers:
        return
    handler = root.handlers[0]
    handler.setFormatter(_ColorFormatter())


class _ColorFormatter(logging.Formatter):
    COLORS = {
        logging.ERROR: "\x1b[31m",
        logging.CRITICAL: "\x1b[31m",
    }

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        color = self.COLORS.get(record.levelno)
        if not color:
            return msg
        return f"{color}{msg}\x1b[0m"


if __name__ == "__main__":
    main()
