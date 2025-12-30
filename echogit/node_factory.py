"""
Choose from file the node type to use, and create the node instance.
"""

from pathlib import Path
from typing import Optional

from echogit.config import Config
from echogit.folder_node import FolderNode
from echogit.node import Node
from echogit.sync.git_sync import GitProjectNode
from echogit.sync.rsync_sync import RsyncProjectNode


def from_path(
    path: Path, *, config: Optional[Config] = None, parent: Optional[Node] = None
) -> Node:
    """
    Instantiate the correct Node subclass for `path`.
    Exactly one of `config` or `parent` must be provided.
    """
    p = Path(path).resolve()
    if (p / ".git").is_dir() or p.suffix == ".git":
        cls = GitProjectNode
    elif (p / ".rsync").is_dir() or p.suffix == ".rsync":
        cls = RsyncProjectNode
    else:
        cls = FolderNode

    if (parent is None) == (config is None):
        raise ValueError("Must pass exactly one of config or parent")
    if parent is not None:
        return cls(path=p, parent=parent)
    return cls(path=p, config=config)
