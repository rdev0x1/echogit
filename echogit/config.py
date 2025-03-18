import configparser
from pathlib import Path


class Config:
    CONFIG_FILE = Path.home() / ".config" / "echogit" / "config.ini"

    def __init__(self, projects_path: Path, git_path: Path | None, remote_name: str):
        self.projects_path = projects_path.expanduser().resolve()
        self.git_path = git_path.expanduser().resolve() if git_path else None
        self.remote_name = remote_name

    @classmethod
    def load(cls, path: Path = CONFIG_FILE) -> "Config":
        path = path.expanduser()
        cfg = configparser.ConfigParser()
        cfg.read(path)

        projects_path = Path(cfg.get("DEFAULT", "projects_path", fallback="~/echogit"))
        git_path = Path(cfg.get("DEFAULT", "git_path", fallback="~/echogit"))
        remote_name = cfg.get("DEFAULT", "remote_name", fallback="origin")

        return cls(
            projects_path=projects_path, git_path=git_path, remote_name=remote_name
        )
