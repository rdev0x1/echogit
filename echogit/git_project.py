import argparse
from echogit.node import Node
from echogit.repository_peer import RepositoryPeer
from echogit.config import Config


class GitProject(Node):
    def __init__(self, path, *, config=None, parent=None):
        name = self._get_folder_name(path)
        super().__init__(name, path=path, parent=parent, config=config)

    def get_type(self):
        return Node.NodeType.GIT_PROJECT

    def scan(self):
        remotes = self.node_config.sync_remotes
        for remote in remotes:
            peer = self.config.get_peer(remote)
            if peer is None:
                print(f"cant sync {remote}. not in: {self.config.get_peers()}")
                continue
            repo = RepositoryPeer(path=self.path, peer=peer,
                                  config=self.config, parent=self)
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


if __name__ == "__main__":
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Synchronize a Git branch with a remote repository")
    parser.add_argument("path", type=str,
                        help="The local path to the Git project")

    # Parse arguments from command line
    args = parser.parse_args()

    config = Config()
    proj = GitProject("project", path=args.path, config=config)
    proj.scan()
    proj.sync()
