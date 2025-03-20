from echogit.node import Node
from echogit.project import Project
from echogit.rsync_repository_peer import RsyncRepositoryPeer


class RsyncProject(Project):
    def __init__(self, path, *, config=None, parent=None):
        super().__init__(path=path, parent=parent, config=config)
        if self.node_config.sync_type != "rsync":
            raise "Invalide rsync project"

    def get_type(self):
        return Node.NodeType.RSYNC_PROJECT

    def createRepositoryPeer(self, peer):
        return RsyncRepositoryPeer(path=self.path, peer=peer,
                                  config=self.config, parent=self)
