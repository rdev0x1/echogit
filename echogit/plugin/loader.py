import importlib.util
import logging
from pathlib import Path

from echogit.config import Config


def load_local_plugins(config: Config):
    plugin_dir = Path(config.plugin_dir).expanduser()

    if not plugin_dir.exists():
        logging.error(f"Plugin directory '{plugin_dir}' does not exist.")
        return

    # Load only specified plugins if provided, otherwise load all available plugins
    available_plugins = {
        folder.name: folder for folder in plugin_dir.iterdir() if folder.is_dir()
    }

    if config.plugins:
        plugins_to_load = config.plugins
    else:
        plugins_to_load = available_plugins.keys()

    for plugin_name in plugins_to_load:
        folder = available_plugins.get(plugin_name)
        if folder is None:
            logging.error(f"Plugin '{plugin_name}' not found in plugin directory")
            continue

        plugin_path = folder / "plugin.py"
        if plugin_path.exists():
            try:
                spec = importlib.util.spec_from_file_location(
                    f"echogit_plugin_{folder.name}", plugin_path
                )

                if spec is None:
                    logging.error(f"Failed to create spec for plugin '{folder.name}'")
                    continue

                loader = spec.loader
                if loader is None:
                    logging.error(f"No loader available for plugin '{folder.name}'")
                    continue

                mod = importlib.util.module_from_spec(spec)
                loader.exec_module(mod)

                if hasattr(mod, "register"):
                    mod.register()
                    logging.info(f"Loaded plugin: {folder.name}")
                else:
                    logging.error(
                        f"Plugin '{folder.name}' has no 'register()' function"
                    )
            except Exception as e:
                logging.error(f"Failed to load plugin {folder.name}: {e}")
        else:
            logging.error(f"Plugin '{folder.name}' does not contain a plugin.py file.")
