from echogit.node import Node


class Project(Node):
    def __init__(self, path, *, config=None, parent=None):
        name = self._get_folder_name(path)
        super().__init__(name, path=path, parent=parent, config=config)

    def createRepositoryPeer(self, _peer):
        raise "Unimplemented"

    def scan(self):
        remotes = self.node_config.sync_remotes
        for remote in remotes:
            peer = self.config.get_peer(remote)
            if peer is None:
                print(f"cant sync {remote}. not in: {self.config.get_peers()}")
                continue
            repo = self.createRepositoryPeer(peer=peer)
            repo.scan()
            self.add_child(repo)

    def sync(self, verbose=False):
        success, total = 0, 0

        for child in self.children:
            child_success, child_total = child.sync(verbose=verbose)
            success += child_success
            total += child_total

        print(f"{self.name}: {success}/{total}")

        # Success is 1 if all children succeeded, otherwise 0
        return int(success == total and total > 0), 1

