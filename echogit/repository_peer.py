from echogit.config import Config
from echogit.peer import Peer
from echogit.sync_branch import SyncBranch
import argparse
from echogit.node import Node


class RepositoryPeer(Node):
    def __init__(self, *, path, peer, config=None, parent=None):
        super().__init__(peer.name, path=path, parent=parent, config=config)
        self.peer = peer

    def scan(self):
        if self.peer.is_down:
            return
        branches = self.node_config.sync_branches
        for branch in branches:
            child = SyncBranch(branch, path=self.path, peer=self.peer,
                               config=self.config, parent=self)
            child.scan()
            self.add_child(child)

    def sync(self, verbose=False):
        if self.peer.config is None and self.peer.is_down == False:
            self.peer.fetch_config()

        config = Config.get_local_instance()
        if self.peer.is_down and config.ignore_peers_down:
            if verbose:
                print(f"Ignore peer {self.peer.name}: is down")
            return 1, 1
        elif self.peer.is_down:
            return 0, 1

        success = 1
        for child in self.children:
            child_success, child_total = child.sync(verbose=verbose)
            if child_success == 0:
                success = 0
        return success, 1


if __name__ == "__main__":
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Synchronize a Git branch with a remote repository")
    parser.add_argument("path", type=str,
                        help="The local path to the Git project")
    parser.add_argument("remote_name", type=str,
                        help="The name of the remote peer to synchronize with")
    parser.add_argument("remote_host", type=str,
                        help="The name of the remote peer to synchronize with")
    parser.add_argument("remote_git_path", type=str,
                        help="The remote repository path (including .git)")

    # Parse arguments from command line
    args = parser.parse_args()

    config = Config()
    peer = Peer(args.remote_name, args.remote_host,
                args.remote_git_path, config=config)
    repo = RepositoryPeer(path=args.path, peer=peer, config=config)
    repo.scan()
    repo.sync()
