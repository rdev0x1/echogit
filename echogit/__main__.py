"""
entry point for Echogit, a program that help you sync your projects using git or rsync.
"""

import argparse
from pathlib import Path

from echogit.config import Config
from echogit.discovery import discover_local_projects
from echogit.node_factory import from_path


def main():
    """
    Echogit entry point
    """
    parser = argparse.ArgumentParser(description="Echogit CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="List local projects")

    sync_parser = subparsers.add_parser("sync", help="Sync local projects")
    sync_parser.add_argument("path", nargs="?", default=None)

    args = parser.parse_args()
    config = Config.load()

    if args.command == "list":
        for proj in discover_local_projects(config.projects_path):
            print(proj)

    elif args.command == "sync":
        path = Path(args.path or config.projects_path)
        root_node = from_path(path, config=config)
        root_node.scan()
        root_node.sync()


if __name__ == "__main__":
    main()
