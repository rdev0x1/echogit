from echogit.node import Node


class GitMissingEchogit(Node):
    def __init__(self, path, *, config=None, parent=None):
        name = self._get_folder_name(path)
        super().__init__(name, path=path, parent=parent, config=config)
        self.node_error = "Git without echogit config"

    def scan(self):
        pass

    def sync(self, verbose=False):
        return self._sync(success=0, total=1)
