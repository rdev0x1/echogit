import os
from echogit.base_config import BaseConfig
from echogit.config import Config


class SyncNodeConfig(BaseConfig):
    SYNC_TYPE_GIT = 'git'
    SYNC_TYPE_RSYNC = 'rsync'

    def __init__(self, project_path, config_file=None, config_string=None):
        super().__init__(config_file, config_string)
        self.project_path = project_path
        self.sync_type = self.config.get(
            "ECHOGIT", "sync_type", fallback=SyncNodeConfig.SYNC_TYPE_GIT)
        self.auto_commit = self.config.getboolean("ECHOGIT", "auto_commit", fallback=False)
        self.sync_branches = self.get_list(
            "BRANCHES", "sync_branches", fallback=[])
        self.sync_remotes = self.get_list(
            "BRANCHES", "sync_remotes", fallback=[])
        self.upstream = self.config.get(
            "BRANCHES", "upstream", fallback="upstream")

    @staticmethod
    def create_default_config(project_path, sync_type=SYNC_TYPE_GIT):
        """Creates a default config in memory and saves it to the given file."""

        # Path to config file
        file_name = os.path.join(project_path, ".echogit", "config.ini")
        if os.path.exists(file_name):
            print(f"Config file already exists at {file_name}. Skipping creation.")
            return

        # Ensure the 'echogit' folder exists
        os.makedirs(os.path.dirname(file_name), exist_ok=True)

        # Get the list of peers as a string
        sync_remotes = Config.get_local_instance().get_peers_as_string()

        # Create the default configuration string
        default_config = f"""
        [ECHOGIT]
        sync_type = {sync_type}
        auto_commit = false

        [BRANCHES]
        sync_branches = master
        sync_remotes = {sync_remotes}
        """

        # Initialize the SyncNodeConfig using the default config string
        config = SyncNodeConfig(project_path, config_string=default_config)

        # Save the initialized config to the file
        config.config_file = file_name
        config.save_to_file()
