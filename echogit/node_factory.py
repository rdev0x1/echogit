from echogit.node import Node
from echogit.config import Config
from echogit.sync_folder import SyncFolder
from echogit.git_project import GitProject
# FIXME: Not yet implemented
# from echogit.rsync_project import RsyncProject
# from echogit.bare_git_repo import BareGitRepo
# from echogit.bare_rsync_repo import BareRsyncRepo


class NodeFactory:
    @staticmethod
    def from_folder(folder_path):
        config = Config.get_local_instance()
        node_type = Node.get_type_from_folder(folder_path)
        if node_type == Node.NodeType.GIT_PROJECT:
            return GitProject(folder_path, config=config)
        # elif node_type == Node.NodeType.RSYNC_PROJECT:
        #    return RsyncProject(folder_path, config=config)
        elif node_type == Node.NodeType.SYNC_FOLDER:
            return SyncFolder(folder_path, config=config)
        # elif node_type == Node.NodeType.BARE_GIT_REPO:
        #    return BareGitRepo(folder_path)
        # elif node_type == Node.NodeType.BARE_RSYNC_REPO:
        #    return BareRsyncRepo(folder_path)
        else:
            raise ValueError(f"Unknown node type for folder: {folder_path}")
