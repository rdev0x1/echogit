import subprocess
from echogit.config import Config
from echogit.node import Node


class RsyncRepositoryPeer(Node):

    def __init__(self, *, path, peer, config=None, parent=None):
        super().__init__(peer.name, path=path, parent=parent, config=config)
        self.peer = peer

    def sync(self, verbose=False):
        """
        Perform a bidirectional sync between self.path and rsync_path
        """
        rsync_options = ['-aur']
        rsync_path = self.peer.get_remote_project_url(self.path)

        # Add verbose flag if requested
        if verbose:
            rsync_options.append('-v')

        if self.peer.config is None and not self.peer.is_down:
            self.peer.fetch_config()

        config = Config.get_local_instance()
        if self.peer.is_down and config.ignore_peers_down:
            if verbose:
                print(f"Ignore peer {self.peer.name}: is down")
            return 1, 1
        elif self.peer.is_down:
            return 0, 1

        try:
            exclusion_options = ["--exclude=.echogit/"]

            # Sync self.path to rsync_path (local to remote)
            # Add extra / at the end of the source.
            # source and source/ create different results:
            # - source  — copy the folder source into destination.
            # - source/ — copy the contents of source into destination.
            if verbose:
                print(f"Syncing {self.path} -> {rsync_path}")
            subprocess.run(['rsync'] + rsync_options + exclusion_options + [self.path + "/", rsync_path], check=True)

            # Sync rsync_path to self.path (remote to local)
            if verbose:
                print(f"Syncing {rsync_path}/ -> {self.path}")
            subprocess.run(['rsync'] + rsync_options + exclusion_options + [rsync_path + "/", self.path], check=True)

            if verbose:
                print("Bidirectional sync completed successfully.")

            return 1, 1
        except subprocess.CalledProcessError as e:
            print(f"Rsync error: {e}")
            return 0, 1
        except Exception as e:
            print(f"An unexpected error occurred: {e}")
            return 0, 1
