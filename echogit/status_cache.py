import os
import configparser
from datetime import datetime


class StatusCache:
    def __init__(self, project_path):
        self.cache_path = os.path.join(
            project_path, ".echogit/status_cache.ini")
        self.errors = {}
        self.stderr = {}
        self.stdout = {}
        self.peer_down = False
        self.cache_date = None

    def cache_status(self, errors, stderr, stdout, peer_down):
        """Store the status information in the cache file."""

        self.cache_date = datetime.now().isoformat()
        self.peer_down = peer_down
        self.stdout = stdout
        self.stderr = stderr
        self.errors = errors

        config = configparser.ConfigParser()
        config['Errors'] = errors
        config['Stderr'] = stderr
        config['Stdout'] = stdout
        config['Meta'] = {
            'peer_down': str(peer_down),
            'cache_date': self.cache_date
        }

        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with open(self.cache_path, 'w') as cache_file:
            config.write(cache_file)

    def load_status(self):
        """Load status from the cache file."""
        if not os.path.exists(self.cache_path):
            return False  # Cache does not exist

        config = configparser.ConfigParser()
        config.read(self.cache_path)

        self.errors = dict(config['Errors'])
        self.stderr = dict(config['Stderr'])
        self.stdout = dict(config['Stdout'])
        self.peer_down = config['Meta'].getboolean('peer_down', False)
        self.cache_date = config['Meta'].get('cache_date')

        if self.peer_down:
            return False

        return True
