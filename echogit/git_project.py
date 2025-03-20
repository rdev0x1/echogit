import argparse
from echogit.git_repository_peer import GitRepositoryPeer
from echogit.config import Config
from echogit.project import Project


class GitProject(Project):
    def __init__(self, path, *, config=None, parent=None):
        super().__init__(path=path, parent=parent, config=config)
        if self.node_config.sync_type != "git":
            raise "Invalide git project"

    def get_type(self):
        return Node.NodeType.GIT_PROJECT

    def createRepositoryPeer(self, peer):
        return GitRepositoryPeer(path=self.path, peer=peer,
                                  config=self.config, parent=self)


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
