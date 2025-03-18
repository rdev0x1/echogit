from functools import cached_property
from pathlib import Path
from typing import Set

from echogit.discovery import ProjectRef, discover_local_projects
from echogit.node import Node
from echogit.sync.git_sync import GitProjectNode


class FolderNode(Node):
    """
    A container node that scans its directory for:
      - Git project roots → ProjectNode
      - Ordinary sub-folders       → FolderNode
    """

    # cache local listing (once)
    _local_cache: Set[Path] = set()

    def __init__(self, path: Path, **kwargs):
        super().__init__(path, **kwargs)

    @cached_property
    def is_folder(self) -> bool:
        # override Node.is_folder if you want to treat
        # bare-repo dirs (.git) as non-folders here
        return True

    def scan(self) -> None:
        """
        Populate just the immediate children of this folder with any project
        worktree or bare-repo one level down under projects_path
        Caches the full local discovery on the first (root) call,
        and reuses it on recursive calls to avoid repeated disk scans.
        """

        self.children.clear()
        cfg = self.config
        data_root = cfg.projects_path

        # On the top-level call (parent is None), build the full local cache
        if self.parent is None:
            # discover all projects under data_root exactly once
            FolderNode._local_cache = set(discover_local_projects(data_root))

        local_all = FolderNode._local_cache
        # determine where we sit within the data tree
        subtree_rel = self.path.relative_to(data_root)

        # collect next‐level children from local projects
        next_children: Set[ProjectRef] = set()
        for ref in local_all:
            if not ref.rel.is_relative_to(subtree_rel):
                continue

            tail = ref.rel.relative_to(subtree_rel).parts[0]
            # take only the very next segment under this folder
            next_children.add(ProjectRef(rel=subtree_rel / tail, type=ref.type))

        # union of local refs and remote‐only refs
        all_children = {ref.rel: ref for ref in next_children}

        # Sort the relative paths so we can peek at the “next” item
        sorted_rels = sorted(all_children.keys())

        # instantiate nodes for each next-level path
        for idx, rel in enumerate(sorted_rels):
            ref = all_children[rel]
            abs_path = data_root / rel

            # Peek at the next relative path (if any) to determine “has_deeper”
            next_rel = sorted_rels[idx + 1] if (idx + 1) < len(sorted_rels) else None
            # if any other child lies under this rel, treat as an intermediate folder
            has_deeper = next_rel is not None and next_rel.is_relative_to(rel)

            if has_deeper:
                NodeCls = FolderNode
            else:
                NodeCls = GitProjectNode

            node = NodeCls(path=abs_path, parent=self)
            node.exists_locally = abs_path.is_dir()
            self.add_child(node)
            node.scan()
