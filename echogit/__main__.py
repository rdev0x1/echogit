"""
entry point for Echogit, a program that help you sync your projects using git or rsync.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
import configparser
import os
from concurrent.futures import ThreadPoolExecutor
import time

from echogit.config import Config
from echogit.discovery import discover_local_projects, discover_remote_projects
from echogit.node_factory import from_path
from echogit.sync.project_node import ProjectNode
from echogit.tui import run_ui


def main():
    """
    Echogit entry point
    """
    parser = argparse.ArgumentParser(description="Echogit CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List local projects")
    list_parser.add_argument(
        "--json",
        action="store_true",
        help="print projects as JSON",
    )
    list_parser.add_argument(
        "--cache-ttl",
        type=int,
        default=30,
        help="cache results for N seconds (0 disables cache)",
    )
    list_remote_parser = subparsers.add_parser("list-remote", help="List remote projects")
    list_remote_parser.add_argument(
        "--json",
        action="store_true",
        help="print projects as JSON",
    )
    list_remote_parser.add_argument(
        "--cache-ttl",
        type=int,
        default=30,
        help="cache results for N seconds (0 disables cache)",
    )

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

    config_parser = subparsers.add_parser("config", help="Get/set configuration")
    config_parser.add_argument("path", nargs="?", default=None)
    config_parser.add_argument(
        "-g",
        "--get",
        action="store_true",
        help="print configuration values",
    )
    config_parser.add_argument(
        "-s",
        "--set",
        dest="set_values",
        default=None,
        help="set values (key:value, key=value)",
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
        _handle_list(config, args.json, args.cache_ttl)
    elif args.command == "list-remote":
        _handle_list_remote(config, args.json, args.cache_ttl)
    elif args.command == "sync":
        _handle_sync(config, args.path, args.progress, args.status)
    elif args.command == "config":
        _handle_config(config, args.path, args.get, args.set_values)
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


def _handle_list(config: Config, as_json: bool, cache_ttl: int) -> None:
    cache_path = _cache_path("list.json")
    if cache_ttl > 0:
        cached = _load_cache(cache_path, cache_ttl)
        if cached and cached.get("projects_path") == str(config.projects_path):
            _print_list_output(cached.get("data", []), as_json)
            return

    projects = [
        {"rel": str(proj.rel), "type": proj.type}
        for proj in discover_local_projects(config.projects_path)
    ]
    if cache_ttl > 0:
        _write_cache(
            cache_path,
            {
                "projects_path": str(config.projects_path),
                "data": projects,
            },
        )
    _print_list_output(projects, as_json)


def _handle_list_remote(config: Config, as_json: bool, cache_ttl: int) -> None:
    cache_path = _cache_path("list-remote.json")
    peers = list(config.peers)
    if cache_ttl > 0:
        cached = _load_cache(cache_path, cache_ttl)
        if cached and cached.get("peers") == peers:
            _print_list_remote_output(cached.get("data", {}), as_json)
            return

    def _collect_remote(peer_name: str) -> list[dict[str, str]]:
        return [
            {"rel": str(proj.rel), "type": proj.type}
            for proj in discover_remote_projects(peer_name)
        ]

    if not peers:
        remote = {}
    else:
        max_workers = min(4, len(peers))
        remote = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {peer: executor.submit(_collect_remote, peer) for peer in peers}
            for peer in peers:
                try:
                    remote[peer] = futures[peer].result()
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logging.error("list-remote failed for %s: %s", peer, exc)
                    remote[peer] = []
    if cache_ttl > 0:
        _write_cache(cache_path, {"peers": peers, "data": remote})
    _print_list_remote_output(remote, as_json)


def _print_list_output(projects: list[dict[str, str]], as_json: bool) -> None:
    if as_json:
        print(json.dumps(projects))
    else:
        for proj in projects:
            print(f"{proj['rel']} ({proj['type']})")


def _print_list_remote_output(
    remote: dict[str, list[dict[str, str]]], as_json: bool
) -> None:
    if as_json:
        print(json.dumps(remote))
    else:
        for peer_name, projects in remote.items():
            print(f"Projects on peer '{peer_name}':")
            for proj in projects:
                print(f"  - {proj['rel']} ({proj['type']})")


def _cache_path(name: str) -> Path:
    base = os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return Path(base) / "echogit" / name


def _load_cache(path: Path, ttl: int) -> dict | None:
    try:
        if not path.is_file():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    created = payload.get("created")
    if created is None or time.time() - created > ttl:
        return None
    return payload


def _write_cache(path: Path, payload: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(payload)
        payload["created"] = time.time()
        path.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        logging.debug("cache write failed for %s", path)


def _handle_sync(
    config: Config, path: str | None, show_progress: bool, show_status: bool
) -> None:
    root = Path(path or config.projects_path)
    root_node = from_path(root, config=config)
    root_node.scan()
    if show_progress:
        def on_progress(node, ok):
            if isinstance(node, ProjectNode):
                if show_status and node.is_dirty():
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


def _handle_config(
    config: Config, path: str | None, do_get: bool, set_values: str | None
) -> None:
    if not do_get and not set_values:
        print("config: use -g or -s")
        sys.exit(2)
    if path:
        _handle_project_config(config, path, do_get, set_values)
    else:
        _handle_global_config(do_get, set_values)


def _parse_kv_list(raw: str) -> dict[str, str]:
    pairs = {}
    for part in raw.split(","):
        item = part.strip()
        if not item:
            continue
        if ":" in item:
            key, val = item.split(":", 1)
        elif "=" in item:
            key, val = item.split("=", 1)
        else:
            continue
        pairs[key.strip()] = val.strip()
    return pairs


def _load_ini(path: Path) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    if path.exists():
        cfg.read(path)
    return cfg


def _write_ini(path: Path, cfg: configparser.ConfigParser) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        cfg.write(f)


def _handle_global_config(do_get: bool, set_values: str | None) -> None:
    cfg_path = Path(os.path.expandvars(Config.CONFIG_FILE)).expanduser()
    cfg = _load_ini(cfg_path)

    if do_get:
        projects_path = cfg.get("DEFAULT", "projects_path", fallback="")
        ignore_peers_down = cfg.getboolean(
            "DEFAULT", "ignore_peers_down", fallback=False
        )
        print(f"Data Path: {projects_path}")
        print(f"Ignore peers down: {ignore_peers_down}")

    if set_values:
        values = _parse_kv_list(set_values)
        if "projects_path" in values:
            cfg.setdefault("DEFAULT", {})
            cfg["DEFAULT"]["projects_path"] = values["projects_path"]
        if "ignore_peers_down" in values:
            cfg.setdefault("DEFAULT", {})
            cfg["DEFAULT"]["ignore_peers_down"] = values["ignore_peers_down"]
        _write_ini(cfg_path, cfg)


def _handle_project_config(
    config: Config, path: str, do_get: bool, set_values: str | None
) -> None:
    project_path = Path(path).expanduser().resolve()
    try:
        rel = project_path.relative_to(config.projects_path)
    except ValueError:
        rel = project_path

    cfg_path = Path(os.path.expandvars(Config.CONFIG_FILE)).expanduser()
    cfg = _load_ini(cfg_path)

    if do_get:
        section = cfg.get("AUTOCOMMIT", "projects", fallback="")
        entries = {
            Path(p.strip())
            for p in section.replace(",", "\n").splitlines()
            if p.strip()
        }
        auto_commit = rel in entries
        print(f"Auto commit: {auto_commit}")

    if set_values:
        values = _parse_kv_list(set_values)
        auto_commit_raw = values.get("autoCommit") or values.get("auto_commit")
        if auto_commit_raw is not None:
            auto_commit = auto_commit_raw.lower() in {"1", "true", "yes", "on"}
            section = cfg.setdefault("AUTOCOMMIT", {})
            current = section.get("projects", "")
            entries = {
                Path(p.strip())
                for p in current.replace(",", "\n").splitlines()
                if p.strip()
            }
            if auto_commit:
                entries.add(rel)
            else:
                entries.discard(rel)
            section["projects"] = ", ".join(sorted(str(p) for p in entries))
            _write_ini(cfg_path, cfg)


if __name__ == "__main__":
    main()
