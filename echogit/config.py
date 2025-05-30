import configparser
from functools import cached_property
from io import StringIO
from pathlib import Path
from typing import List

from echogit.utils import is_peer_reachable, run_ssh_command


class Config:
    CONFIG_FILE = Path.home() / ".config" / "echogit" / "config.ini"
    config_peers = {}

    # git_path can be None to support low memory device like smartphone
    def __init__(
        self,
        projects_path: Path,
        git_path: Path | None,
        peers: List[str],
        peer_allowed_paths: dict[str, List[Path]],
    ):
        self.projects_path = projects_path.expanduser().resolve()
        self.git_path = git_path.expanduser().resolve() if git_path else None
        self._all_peers = peers
        self.peer_allowed_paths = peer_allowed_paths

    @cached_property
    def peers(self) -> List[str]:
        """
        Return only the peers we can actually reach over SSH.
        """
        reachable = []
        for peer in self._all_peers:
            if is_peer_reachable(peer):
                reachable.append(peer)
        return reachable

    @classmethod
    def get_config_peer(cls, peer_name: str) -> "Config | None":
        if peer_name in cls.config_peers:
            return cls.config_peers[peer_name]

        success, cfg_txt = run_ssh_command(peer_name, f"cat {Config.CONFIG_FILE}")
        if not success:
            return None
        rconfig = Config.load_from_buffer(cfg_txt)
        cls.config_peers[peer_name] = rconfig
        return rconfig

    @classmethod
    def _load(cls, cfg: configparser.ConfigParser) -> "Config":
        projects_path = Path(cfg.get("DEFAULT", "projects_path", fallback="~/echogit"))
        git_path = Path(cfg.get("DEFAULT", "git_path", fallback="~/echogit"))
        peers = [
            p.strip()
            for p in cfg.get("PEERS", "peers", fallback="").split(",")
            if p.strip()
        ]

        peer_allowed_paths = {}
        for peer in peers:
            allowed = cfg.get(peer, "allowed_paths", fallback=None)
            if not allowed:
                continue

            rel_list = [Path(p.strip()) for p in allowed.split(",")]
            peer_allowed_paths[peer] = [
                (projects_path / Path(rel)).resolve() for rel in rel_list
            ]

        return cls(
            projects_path=projects_path,
            git_path=git_path,
            peers=peers,
            peer_allowed_paths=peer_allowed_paths,
        )

    @classmethod
    def load_from_file(cls, path: Path = CONFIG_FILE) -> "Config":
        path = path.expanduser()
        cfg = configparser.ConfigParser()
        cfg.read(path)

        return Config._load(cfg)

    @classmethod
    def load_from_buffer(cls, config_string: str) -> "Config":
        cfg = configparser.ConfigParser()
        config_buffer = StringIO(config_string)
        cfg.read_file(config_buffer)

        return Config._load(cfg)

    def is_path_allowed(self, peer_name: str, path: Path) -> bool:
        allowed_paths = self.peer_allowed_paths.get(peer_name)
        if not allowed_paths:
            return True  # If no rules, everything allowed
        return any(
            path.is_relative_to(self.projects_path / allowed)
            for allowed in allowed_paths
        )
