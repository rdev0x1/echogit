from echogit.node import Node


class BareRsyncRepo(Node):
    def __init__(self, path, *, config=None, parent=None):
        name = self._get_folder_name(path).removesuffix(".rsync")
        super().__init__(name, path=path, parent=parent, config=config)

    def scan(self):
        pass

    def sync(self, verbose=False):
        pass
