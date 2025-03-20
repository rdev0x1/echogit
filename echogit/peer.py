import ast
import json
import os
import re
import socket
import sys
import subprocess
from echogit.config import Config
from echogit.version import Version


class Peer:
    def __init__(self, name=None, host=None, git_path=None, config=None):
        self.priority = 0
        self.host = host  # IP or hostname
        self.name = name
        self.git_path = git_path
        self.version = "0.0.1"
        self.config = config
        self.is_down = False

        # Cache directory based on XDG specification
        self.cache_dir = self._get_cache_dir()

    def _get_cache_dir(self):
        """
        Get the XDG cache directory, or fallback to home directory.
        """
        xdg_cache_home = os.getenv(
            "XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
        cache_dir = os.path.join(xdg_cache_home, "echogit", "peers")
        os.makedirs(cache_dir, exist_ok=True)
        return cache_dir

    def _get_cache_file(self):
        """
        Get the cache file path for the peer.
        """
        return os.path.join(self.cache_dir, f"{self.name}_projects.json")

    def is_localhost(self):
        """
        Check if the given host is localhost, covering common localhost IPs,
        hostname resolution, and /etc/hosts entries.
        """
        if hasattr(self, '_is_localhost') and self._is_localhost is not None:
            return self._is_localhost

        if self.is_down:
            self._is_localhost = False
            return False

        # Common localhost values
        localhost_ips = ['127.0.0.1', '::1']
        localhost_names = ['localhost', socket.gethostname(), socket.getfqdn()]

        try:
            addr_info = socket.getaddrinfo(self.host, None)
            host_ips = [info[4][0] for info in addr_info]

            if self.host in localhost_names or any(ip in localhost_ips for ip in host_ips):
                self._is_localhost = True
                return True

            local_ips = socket.gethostbyname_ex(socket.gethostname())[2]
            self._is_localhost = any(ip in local_ips for ip in host_ips)
            return self._is_localhost

        except socket.error:
            self._is_localhost = False
            return False

    def load_from_string(self, peer_data):
        """
        Load peer data from a formatted string.
        Format: name:host:priority
        """
        data = peer_data.split(':')
        if len(data) == 3:
            self.name, self.host, self.priority = data[0].strip(
            ), data[1].strip(), int(data[2].strip())
        else:
            raise ValueError("Peer data is not in the correct format")

    def _fetch_remote_config(self):
        """
        Fetches the config file from the remote peer via SSH.
        """
        remote_config_path = "~/.config/echogit/config.ini"
        fetch_command = f"cat {remote_config_path}"
        config_content = self._execute_remote_command(fetch_command)

        if config_content:
            self.config = Config(config_string=config_content)
            self.config.add_ssh_prefix_to_git_path(self.name)
        else:
            self.is_down = True

        # get remote version
        remote_version_str = self._execute_echogit_remote_command("version")

        if remote_version_str is None:
            self.is_down = True
        elif not Version.is_compatible(remote_version_str):
            print(f"peer {self.name} is incompatible: {remote_version_str}")
            self.is_down = False

    def fetch_config(self):
        if self.is_localhost():
            self.config = Config.get_local_instance()
        else:
            self._fetch_remote_config()

    def get_version(self):
        result = self._execute_echogit_remote_command("version")
        if result is None:
            return None

        lines = result.splitlines()
        for line in lines:
            if line.startswith("version="):
                return line.split("=", 1)[1].strip()

        # Return None if no version string is found
        return None

    def get_remote_project_url(self, path):
        """
        Return the ssh address of a project located at the path folder.
        This is used by git clone or git remote add.
        """
        if self.is_down:
            return None

        self._fetch_config_if_needed()
        if self.config is None:
            return None

        data_path = Config.get_local_instance().projects_path
        if not path.startswith(data_path):
            raise ValueError(f"project_path {path} must start with data_path: {data_path}")

        # Determine the relative project path
        relative_project_path = os.path.relpath(path, data_path)
        project_base_path = os.path.join(self.config.git_path, relative_project_path)

        sync_type = self._determine_sync_type(project_base_path)
        if sync_type is None:
            raise ValueError(f"No .git or .rsync directory found for the project at {project_base_path}")

        if sync_type == "rsync":
            # rsync don't understand url when started with ssh://
            project_base_path = re.sub("^ssh://", "", project_base_path)


        return f"{project_base_path}.{sync_type}"

    def _fetch_config_if_needed(self):
        """Fetch config if it's not already loaded."""
        if self.config is None:
            self.fetch_config()

    def _determine_sync_type(self, project_base_path):
        """
        Determine the sync type ('git' or 'rsync') by checking the folder's existence
        locally or remotely depending on whether the peer is localhost.
        """
        if self.is_localhost():
            if os.path.isdir(f"{project_base_path}.git"):
                return "git"
            if os.path.isdir(f"{project_base_path}.rsync"):
                return "rsync"
        else:
            if self._remote_directory_exists(f"{project_base_path}.git"):
                return "git"
            if self._remote_directory_exists(f"{project_base_path}.rsync"):
                return "rsync"
        return None

    def _remote_directory_exists(self, ssh_directory_path):
        """Check if a directory exists on a remote peer via SSH."""
        # ssh_directory_path start with ssh://peer_name:. Remove it
        directory_path = ssh_directory_path.split(":")[-1]
        return self._execute_remote_command(f"test -d {directory_path}") is not None

    def get_remote_projects(self, cached):
        """
        Retrieve the remote projects, either from cache or by running the
        command remotely.
        """
        if cached:
            cached_projects = self._load_cached_projects()
            if cached_projects:
                return cached_projects

        self._fetch_config_if_needed()

        # If not using cache or cache is missing, fetch remote projects
        projects = self._fetch_remote_projects()
        if projects:
            self._save_projects_to_cache(projects)

        return projects

    def _fetch_remote_projects(self):
        """
        Fetch remote bare repositories using SSH and return them as a
        dictionary.
        """
        result = self._execute_echogit_remote_command("list")

        if not result:
            self.is_down = True
            return {}

        # Remove 'repo = ' prefix if present
        result = result.strip()
        if result.startswith("Local projects: "):
            result = result[len("Local projects: "):].strip()

        # Safely evaluate the result as a dictionary
        try:
            repo_dict = ast.literal_eval(result)
        except (SyntaxError, ValueError):
            self.is_down = True
            return {}

        # Rebuild the dictionary with paths ending in .git or .rsync
        bare_repo_dict = {
            path: project_name
            for path, project_name in repo_dict.items()
            if path.endswith('.git/') or path.endswith('.rsync/')
        }

        return bare_repo_dict

    def _load_cached_projects(self):
        """
        Load cached projects from the local cache file.
        """
        cache_file = self._get_cache_file()

        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    cached_data = json.load(f)
                    return cached_data
            except (json.JSONDecodeError, IOError):
                print(
                    f"Failed to load cache from {cache_file}. Ignoring cache", file=sys.stderr)

        return None

    def _save_projects_to_cache(self, projects):
        """
        Save the projects to a local cache file.
        """
        cache_file = self._get_cache_file()

        try:
            with open(cache_file, "w") as f:
                json.dump(projects, f)
        except IOError:
            print(f"Failed to write cache to {cache_file}.", file=sys.stderr)

    def _execute_remote_command(self, command):
        """
        Executes a remote command via SSH and returns the output.
        """
        if self.is_down:
            return None

        ssh_command = ['ssh', self.host, command]

        try:
            result = subprocess.run(
                ssh_command, capture_output=True, text=True, check=True)
            return result.stdout

        except OSError as e:
            # Handle network-related errors like unreachable host, DNS issues, etc.
            host = self.host
            self.is_down = True
            print(f"Network error: Peer {host} is unreachable: {e}", file=sys.stderr)
            return None

        except subprocess.CalledProcessError as e:
            # Handle other errors (command executed but failed)
            host = self.host
            print(f"Error executing remote command '{command}' on {host}: {e}", file=sys.stderr)
            return None

    def _execute_echogit_remote_command(self, command):
        if self.is_down:
            return None

        full_command = f"python3 {self.config.echogit_bin} {command}"
        return self._execute_remote_command(full_command)
