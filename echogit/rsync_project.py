from echogit.node import Node


class RsyncProject(Node):
    def __init__(self, path, *, config=None, parent=None):
        name = self._get_folder_name(path)
        super().__init__(name, path=path, parent=parent, config=config)
        pass
