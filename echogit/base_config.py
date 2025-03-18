import configparser
from io import StringIO


class BaseConfig:
    def __init__(self, config_file=None, config_string=None):
        self.config_file = config_file
        self.config = configparser.ConfigParser()

        if config_string:
            self.load_from_string(config_string)
        elif config_file:
            self.load_from_file(config_file)
        else:
            raise ValueError(
                "Either config_file or config_string must be provided")

    def load_from_file(self, config_file):
        """Load the configuration from a file."""
        with open(config_file, "r") as f:
            self.config.read_file(f)

    def save_to_file(self):
        """Save the configuration to file."""
        if self.config_file is None:
            raise ValueError("Cannot save to file if filename is not provided")
        with open(self.config_file, "w") as f:
            self.config.write(f)

    def load_from_string(self, config_string):
        """Load the configuration from a string buffer."""
        config_buffer = StringIO(config_string)
        self.config.read_file(config_buffer)

    def get_list(self, section, option, fallback=None):
        """
        Get a list from a config option.

        @param section: The config section.
        @param option: The config option.
        @param fallback: The fallback value if the option is not found.
        @return: The list of values, or the fallback.
        """
        value = self.config.get(section, option, fallback=fallback)
        if value is None or value == "" or not value:
            return fallback
        return [item.strip() for item in value.split(",")]
