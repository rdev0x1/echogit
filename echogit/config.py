import os
from echogit.base_config import BaseConfig


class Config(BaseConfig):
    _local_instance = None

    def __init__(self, config_file=None, config_string=None):
        """
        Initialize the configuration.

        @param config_path: Optional path to the configuration file.
        """
        if config_file is None and config_string is None:
            raise ValueError("Cannot create Config")
        super().__init__(config_file, config_string)

        # path where projects are saved
        self.projects_path = self.config.get(
            'DEFAULT', 'projects_path', fallback='~/data/')
        self.projects_path = os.path.expanduser(self.projects_path)

        # path where projects' git repositories are saved
        self.git_path = self.config.get('DEFAULT', 'git_path', fallback=None)
        if self.git_path:
            self.git_path = os.path.expanduser(self.git_path)

        self.git_path = self._ensure_trailing_slash(self.git_path)
        self.projects_path = self._ensure_trailing_slash(self.projects_path)
        self.echogit_bin = self.config.get(
            'DEFAULT', 'echogit_bin', fallback=None)
        self.ignore_peers_down = self.config.getboolean(
            'DEFAULT', 'ignore_peers_down', fallback=False)

        # list of folder that are collapsed at startup. Needed on UI for example.
        # collapsed folder contains projects we are not interested in.
        # We still can open the folder.
        self.collapse_folders = self.get_list(
            'DEFAULT', 'collapse_folders', fallback=[])

        self._peers = {}
        # self.peers = self._load_peers()

    @classmethod
    def get_local_instance(cls):
        """
        Return the singleton instance for the local peer.
        If it doesn't exist, create it.
        """
        if cls._local_instance is None:
            config_file = os.path.expanduser('~/.config/echogit/config.ini')
            cls._local_instance = cls(config_file=config_file)
        return cls._local_instance

    # Do not use on remote peer
    def get_peers(self):
        if self._peers:
            return self._peers
        else:
            self._peers = self._load_peers()
            return self._peers

    def get_peers_as_string(self):
        return ", ".join(self._peers)

    def get_peer(self, peer_name):
        peers = self.get_peers()

        if peer_name not in peers:
            return None

        return peers[peer_name]

    def _ensure_trailing_slash(self, path):
        if path is None:
            return None
        return path if path.endswith('/') else path + '/'

    def add_ssh_prefix_to_git_path(self, peer_name):
        self.git_path = "ssh://" + peer_name + ":" + self.git_path

    def _load_peers(self):
        """
        Load peer configurations from the config file and return a list of Peer objects.
        Uses the _get_list helper to parse peers.
        """
        # FIXME: Clean this mess
        # Delay the import to avoid circular import issues
        # Kids, don't do this that home.
        from echogit.peer import Peer

        # Get list of peer strings from the config
        peer_strings = self.get_list('PEERS', 'peers', fallback=[])

        print(f"load peers f{peer_strings}")
        peers = {}
        for peer_data in peer_strings:
            peer = Peer()
            peer.load_from_string(peer_data)
            peers[peer.name] = peer
        return peers

    def print(self):
        print(f"Data Path: {self.projects_path}")
        print(f"Ignore peers down: {self.ignore_peers_down}")
        print(f"Git Path: {self.git_path}")


if __name__ == "__main__":
    test_path = os.path.dirname(os.path.realpath(__file__))
    test_path = os.path.join(test_path, "../test_dir/config/config_test.ini")
    config = Config(test_path)
    print(f"Projects Path: {config.projects_path}")
    print(f"Git Path: {config.git_path}")
    print(f"collapse folders: {config.collapse_folders}")

    print(f"Peers: {[f'{peer.name} (Priority: {peer.priority}, Host: {peer.host})' for _key, peer in config.peers.items()]}")
