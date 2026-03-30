"""
Configuration loader for Echogit.

Handles projects_path, git_path, peers, and allowed_paths.
"""

from __future__ import annotations

import configparser
import os
from functools import cached_property
from io import StringIO
from pathlib import Path
from typing import List, Set

from echogit.utils import is_peer_reachable, run_ssh_command


class Config:
    """
    Holds Echogit configuration loaded from file or buffer.

    Attributes:
        projects_path: root folder for local projects
        git_path: base folder for bare Git repos
        peers: list of peer hostnames
        peer_allowed_paths: mapping of peer→allowed subpaths
    """

    CONFIG_FILE = "$HOME/.config/echogit/config.ini"
    config_peers = {}

    # git_path can be None to support low memory device like smartphone
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(
        self,
        projects_path: Path,
        git_path: Path | None,
        peers: List[str],
        peer_allowed_paths: dict[str, List[Path]],
        auto_commit_projects: Set[Path],
        ignore_peers_down: bool,
        *,
        expand_paths: bool = True,
        home_dir: Path | None = None,
    ):
        if expand_paths:
            if home_dir is None:
                self.projects_path = projects_path.expanduser().resolve()
                self.git_path = git_path.expanduser().resolve() if git_path else None
            else:
                self.projects_path = _expand_path_for_home(projects_path, home_dir)
                self.git_path = (
                    _expand_path_for_home(git_path, home_dir) if git_path else None
                )
        else:
            self.projects_path = projects_path
            self.git_path = git_path
        self._all_peers = peers
        self.peer_allowed_paths = peer_allowed_paths
        self.auto_commit_projects = auto_commit_projects
        self.ignore_peers_down = ignore_peers_down

    @cached_property
    def peers(self) -> List[str]:
        """
        Return only the peers we can actually reach over SSH.
        """
        if self.ignore_peers_down:
            return list(self._all_peers)
        return [peer for peer in self._all_peers if is_peer_reachable(peer)]

    @classmethod
    def get_config_peer(cls, peer_name: str) -> "Config | None":
        if peer_name in cls.config_peers:
            return cls.config_peers[peer_name]

        success, cfg_txt = run_ssh_command(peer_name, f"cat {Config.CONFIG_FILE}")
        if not success:
            return None
        home_dir = None
        home_success, home_out = run_ssh_command(peer_name, "printf '%s' \"$HOME\"")
        if home_success and home_out.strip():
            home_dir = Path(home_out.strip())
        if home_dir is None:
            rconfig = Config.load_from_buffer(cfg_txt, expand_paths=False)
        else:
            rconfig = Config.load_from_buffer(
                cfg_txt, expand_paths=True, home_dir=home_dir
            )
        cls.config_peers[peer_name] = rconfig
        return rconfig

    @classmethod
    def _load(
        cls,
        cfg: configparser.ConfigParser,
        *,
        expand_paths: bool = True,
        home_dir: Path | None = None,
    ) -> "Config":
        """
        Parse a ConfigParser into a Config instance.
        """
        projects_path = Path(cfg.get("DEFAULT", "projects_path", fallback="~/echogit"))
        git_path = Path(cfg.get("DEFAULT", "git_path", fallback="~/echogit"))
        peers = _split_csv(cfg.get("PEERS", "peers", fallback=""))

        peer_allowed_paths = {}
        for peer in peers:
            allowed = cfg.get(peer, "allowed_paths", fallback=None)
            if not allowed:
                continue

            rel_list = [Path(p) for p in _split_csv(allowed)]
            peer_allowed_paths[peer] = [
                (projects_path / Path(rel)).resolve() for rel in rel_list
            ]

        # Parse the [AUTOCOMMIT] section
        auto_commit_projects: Set[Path] = set()
        if cfg.has_section("AUTOCOMMIT"):
            raw_list = cfg.get("AUTOCOMMIT", "projects", fallback="")
            # Each entry can be comma-separated or newline-separated
            for item in _split_lines(raw_list):
                p = item.strip()
                if not p:
                    continue
                # interpret path relative to projects_path
                rel = Path(p)
                auto_commit_projects.add(rel)

        ignore_peers_down = cfg.getboolean(
            "DEFAULT", "ignore_peers_down", fallback=False
        )

        return cls(
            projects_path=projects_path,
            git_path=git_path,
            peers=peers,
            peer_allowed_paths=peer_allowed_paths,
            auto_commit_projects=auto_commit_projects,
            ignore_peers_down=ignore_peers_down,
            expand_paths=expand_paths,
            home_dir=home_dir,
        )

    @classmethod
    def load_from_file(cls, path: Path | None = None) -> "Config":
        """
        Load configuration from an .ini file on disk.
        """
        if path is None:
            # expand $HOME locally
            path = Path(os.path.expandvars(cls.CONFIG_FILE)).expanduser()
        else:
            path = path.expanduser()

        cfg = configparser.ConfigParser()
        cfg.read(path)
        return Config._load(cfg)

    @classmethod
    def load_from_buffer(
        cls,
        config_string: str,
        *,
        expand_paths: bool = True,
        home_dir: Path | None = None,
    ) -> "Config":
        """
        Load configuration from a string buffer.

        :param config_string: INI-formatted text
        :returns: Config instance
        """
        cfg = configparser.ConfigParser()
        config_buffer = StringIO(config_string)
        cfg.read_file(config_buffer)

        return Config._load(cfg, expand_paths=expand_paths, home_dir=home_dir)

    def is_path_allowed(self, peer_name: str, path: Path) -> bool:
        """
        return True if path can be synced with peer_name
        """
        allowed_paths = self.peer_allowed_paths.get(peer_name)
        if not allowed_paths:
            return True  # If no rules, everything allowed
        return any(
            path.is_relative_to(self.projects_path / allowed)
            for allowed in allowed_paths
        )


def _split_csv(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _split_lines(raw: str) -> list[str]:
    return [item.strip() for item in raw.replace(",", "\n").splitlines() if item.strip()]


def _expand_path_for_home(raw: Path, home_dir: Path) -> Path:
    raw_str = str(raw)
    if raw_str == "~":
        raw_str = str(home_dir)
    elif raw_str.startswith("~/"):
        raw_str = str(home_dir / raw_str[2:])
    p = Path(raw_str)
    if not p.is_absolute():
        p = home_dir / p
    return p
