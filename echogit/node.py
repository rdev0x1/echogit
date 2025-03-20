import os
from enum import Enum
from echogit.sync_node_config import SyncNodeConfig


class Node:
    class NodeType(Enum):
        SYNC_FOLDER = "SyncFolder"
        GIT_PROJECT = "GitProject"
        RSYNC_PROJECT = "RsyncProject"
        BARE_GIT_REPO = "BareGitRepo"
        BARE_RSYNC_REPO = "BareRsyncRepo"
        UNKNOWN = "Unknown"

    def __init__(self, name, *, path=None, parent=None, config=None):
        self.name = name
        self.path = path
        self.children = []
        self.parent = parent
        self.config = config
        self.collapse = False

        config_file = os.path.join(path, ".echogit/config.ini")

        # Convert relative path to absolute if necessary. (mainly for unit test)
        if not os.path.isabs(config_file):
            # Assuming the relative path is based on the current script directory
            config_file = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "../", config_file))

        if os.path.exists(config_file):
            self.node_config = SyncNodeConfig(path, config_file)
        elif parent:
            # if current node has no echogit config then
            # inherit from parent's config
            self.node_config = parent.node_config
        else:
            self.node_config = None

    def get_type(self):
        return Node.NodeType.UNKNOWN

    def _get_folder_name(self, path):
        # Expand '~' to the full home directory path
        path = os.path.expanduser(path)

        # Resolve "." or ".." to absolute paths
        path = os.path.abspath(path)

        # Get the folder name from the path
        folder_name = os.path.basename(path)

        return folder_name

    @staticmethod
    def _has_subdirectory(path, subdir):
        return os.path.isdir(os.path.join(path, subdir))

    @staticmethod
    def _is_git_project(path):
        return Node._has_subdirectory(path, ".git")

    @staticmethod
    def _is_echogit_git_project(path):
        return Node._has_subdirectory(path, ".echogit") and \
            Node._has_subdirectory(path, ".git")

    @staticmethod
    def _is_echogit_rsync_project(path):
        return Node._has_subdirectory(path, ".echogit") and \
            not Node._has_subdirectory(path, ".git") and \
            Node.get_type_from_config(path) == Node.NodeType.RSYNC_PROJECT

    @staticmethod
    def get_type_from_config(path):
        config_file = os.path.join(path, ".echogit/config.ini")
        sync_type = SyncNodeConfig.get_sync_type_from_config(config_file)
        if sync_type == SyncNodeConfig.SYNC_TYPE_GIT:
            return Node.NodeType.GIT_PROJECT
        elif sync_type == SyncNodeConfig.SYNC_TYPE_RSYNC:
            return Node.NodeType.RSYNC_PROJECT
        else:
            return Node.NodeType.UNKNOWN

    @staticmethod
    def get_type_from_folder(folder_path):
        folder_name = os.path.basename(folder_path)
        if not os.path.isdir(folder_path):
            return Node.NodeType.UNKNOWN
        elif folder_name == ".echogit":
            return Node.NodeType.UNKNOWN
        # folder ending .git are bare git used for repository. Not working project
        # Same for .rsync folders. See readme for more information.
        elif folder_path.endswith(".git"):
            return Node.NodeType.BARE_GIT_REPO
        elif folder_path.endswith(".rsync"):
            return Node.NodeType.BARE_RSYNC_REPO
        elif Node._is_echogit_git_project(folder_path):
            return Node.NodeType.GIT_PROJECT
        elif Node._is_echogit_rsync_project(folder_path):
            return Node.NodeType.RSYNC_PROJECT
        elif Node._is_git_project(folder_path):
            return Node.NodeType.UNKNOWN
        else:
            return Node.NodeType.SYNC_FOLDER

    def get_children_tree_by_path(self):
        tree = {}

        start_path = self.config.git_path
        if start_path is None:
            start_path = self.config.projects_path

        # FIXME
        path = self.config._ensure_trailing_slash(self.path)

        if path.startswith(start_path):
            # Remove git_path and the leading slash from the full_path
            path = path[len(start_path):].lstrip(os.sep)
        else:
            raise ValueError(
                f"The path '{path}' does not start with '{start_path}'.")
        tree[path] = self.name
        return tree

    def print_path(self):
        tree = self.get_children_tree_by_path()
        for path, node in tree.items():
            print(f"{node}, {path}")

    def add_child(self, child):
        child.parent = self
        self.children.append(child)

    def get_project_state_str(self):
        key_flag = {"remote_add": "R", "push": "P", "pull": "L", "status": "D"}
        errors = self.get_errors()

        if errors:
            return ",".join(key_flag[key] for key in errors if key in key_flag)

        self.collapse = True
        return "OK"

    def get_errors(self):
        errors = {}
        for child in self.children:
            for key, value in child.get_errors().items():
                if value != 0:
                    errors[key] = value
        return errors

    def print(self):
        print(f"{self.name}:[{self.get_project_state_str()}]")

    def has_error(self):
        return any(child.has_error() for child in self.children)

    def get_logs(self):
        _str = f"{self.name}\n"
        for child in self.children:
            _str += child.get_logs() + "\n"
        return _str

    def is_folder(self):
        return False

    def scan(self):
        pass

    def sync(self, verbose=False):
        raise NotImplementedError("Subclasses must implement sync method.")
