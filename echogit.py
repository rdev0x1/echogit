import os
import subprocess
import argparse
from echogit.config import Config
from echogit.tui import run_ui
from echogit.node_factory import NodeFactory
from echogit.version import Version
from echogit.sync_node_config import SyncNodeConfig
from echogit.node import Node


def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="Echogit CLI")
    subparsers = parser.add_subparsers(dest="command")

    # sync command
    sync_parser = subparsers.add_parser("sync", help="Synchronize projects")
    sync_parser.add_argument("folder", nargs="?", default=None,
                             help="Folder to sync")
    sync_parser.add_argument("-v", "--verbose", action="store_true",
                             help="Verbose output")
    sync_parser.add_argument("-p", "--peer", default=None,
                             help="Specify a peer to sync with")

    # clone command
    clone_parser = subparsers.add_parser("clone", help="Clone a project")
    clone_parser.add_argument("folder", help="Folder to clone")
    clone_parser.add_argument("-p", "--peer", default=None,
                              help="Specify a peer to clone from")

    # config command
    config_parser = subparsers.add_parser("config", help="Show configuration")
    config_parser.add_argument("folder", nargs="?", default=None,
                             help="Folder to sync")
    config_parser.add_argument(
        "-g", "--get", action="store_true", help="Get the configuration")
    config_parser.add_argument(
        "-s", "--set", nargs="?", default=None, help="Set configuration values in the format 'ignore_peers_down:true,projects_path:/tmp/toto/'")

    # list command
    list_parser = subparsers.add_parser("list", help="List projects")
    list_parser.add_argument(
        "folder", nargs="?", default=None, help="Folder to list")
    list_parser.add_argument(
        "--remote", action="store_true", help="List remote projects")
    list_parser.add_argument("-p", "--peer", default=None,
                             help="Specify a peer for remote listing")
    list_parser.add_argument(
        "-c", "--cached", action="store_true", help="Use cached data")

    # tui command
    subparsers.add_parser("tui", help="Launch TUI interface")

    # version command
    version_parser = subparsers.add_parser("version", help="Print version")
    version_parser.add_argument("-p", "--peer", default=None,
                             help="Specify a peer for remote listing")
    version_parser.add_argument(
        "-c", "--cached", action="store_true", help="Use cached data")

    # peers command
    peers_parser = subparsers.add_parser("peers", help="List available peers")
    peers_parser.add_argument(
        "-v", "--verbose", action="store_true", help="Verbose output")

    # Parse command-line arguments
    args = parser.parse_args()

    if args.command == "config":
        handle_config_command(args)
    elif args.command == "version":
        handle_version_command(args.peer, args.cached)
    elif args.command == "sync":
        config = Config.get_local_instance()
        folder = args.folder or config.projects_path
        handle_sync_command(folder, args.verbose)
    elif args.command == "clone":
        folder = args.folder
        handle_clone_command(folder, args.peer)
    elif args.command == "tui":
        run_ui()
    elif args.command == "list":
        config = Config.get_local_instance()
        folder = args.folder or config.git_path or config.projects_path
        handle_list_command(folder, args.remote, args.peer, args.cached)
    elif args.command == "peers":
        handle_peers_command(args.verbose)
    else:
        print("Unknown command")
        print_usage()


def print_usage():
    print("Usage: echogit <command> [options]")
    print("Commands:")
    print("  sync           - Synchronize projects")
    print("  clone          - Clone a project")
    print("  config         - Show configuration")
    print("  list           - List projects (local or remote)")
    print("  peers          - List available peers")
    print("  version        - Print version")


def _parse_set_string(set_string):
    """
    Parse the input string in the format 'ignore_peers_down:true,projects_path:/tmp/toto/'
    into a dictionary.
    """
    config_updates = {}

    if not set_string:
        return config_updates

    pairs = set_string.split(",")
    for pair in pairs:
        key, value = pair.split(":")
        key = key.strip()
        value = value.strip()

        # Convert "true"/"false" to boolean for ignore_peers_down
        if key == "ignore_peers_down" or key == "auto_commit":
            if value.lower() in ['true', 'yes', '1']:
                config_updates[key] = True
            elif value.lower() in ['false', 'no', '0']:
                config_updates[key] = False
            else:
                raise ValueError(f"Invalid value for {key}: {value}")
        else:
            config_updates[key] = value

    return config_updates


def _handle_echogit_config_command(args):
    config = Config.get_local_instance()
    if args.set:
        # Parse the set string
        config_updates = _parse_set_string(args.set)

        # Update the config in the [DEFAULT] section
        if 'projects_path' in config_updates:
            config.config.set('DEFAULT', 'projects_path', config_updates['projects_path'])
            config.projects_path = config_updates['projects_path']
        if 'ignore_peers_down' in config_updates:
            config.config.set('DEFAULT', 'ignore_peers_down', str(config_updates['ignore_peers_down']))
            config.ignore_peers_down = config_updates['ignore_peers_down']

        # Save the updated config if needed
        config.save_to_file()

    # If `--get` was used or `--set` was not provided
    if args.get or not args.set:
        config.print()


def _handle_project_config_command(args):
    node = NodeFactory.from_folder(args.folder)
    if node.get_type() != Node.NodeType.GIT_PROJECT and node.get_type() != Node.NodeType.RSYNC_PROJECT:
        print(f"Invalid project {args.folder}, type={node.get_type()}")
        return -1
    config = node.node_config

    if args.set:
        # Parse the set string
        config_updates = _parse_set_string(args.set)

        # Update the config in the [DEFAULT] section
        if 'auto_commit' in config_updates:
            config.config.set('DEFAULT', 'auto_commit', str(config_updates['auto_commit']))
            config.auto_commit = config_updates['auto_commit']

        # Save the updated config if needed
        config.save_to_file()

    # If `--get` was used or `--set` was not provided
    if args.get or not args.set:
        # Display current config
        config.print()


def handle_config_command(args):
    if args.folder is None:
        _handle_echogit_config_command(args)
    else:
        _handle_project_config_command(args)


def handle_version_command(peer_str, cached):
    config = Config.get_local_instance()
    if peer_str is None:
        version = Version.full_version()
    elif peer_str in config.get_peers():
        peer = config.get_peer(peer_str)
        version = peer.get_version()
    else:
        print(f"invalid peer {peer_str}")
        return
    print(version)


def _get_root_node(folder):
    try:
        node = NodeFactory.from_folder(folder)
    except ValueError as e:
        print(f"{folder} is not an echogit project")
        return None

    node.scan()
    return node


def handle_sync_command(folder, verbose):
    node = _get_root_node(folder)
    if node is None:
        return
    print(f"Syncing {node.name}...")
    success, total = node.sync(verbose=verbose)
    print(f"done on {success}/{total}...")


def _clone_project(folder, peers):
    sync_type = SyncNodeConfig.SYNC_TYPE_UNKNOWN
    for peer in peers:
        remote_url = peer.get_remote_project_url(folder)

        if peer.is_down:
            print(f"Skipping peer {peer.name}: peer is down")
            continue

        if not remote_url:
            print(f"Skipping peer {peer.name}: no valid remote URL found for {folder}")
            continue

        print(f"Attempting to sync from peer {peer.name} / {remote_url}")

        # Determine the sync type based on the URL's extension
        if remote_url.endswith('.git'):
            sync_type = SyncNodeConfig.SYNC_TYPE_GIT
            command = ["git", "clone", "--origin", peer.name, remote_url, folder]
        elif remote_url.endswith('.rsync'):
            command = ["rsync", "-avz", f"{remote_url}/", folder]
            sync_type = SyncNodeConfig.SYNC_TYPE_RSYNC
        else:
            print(f"Unknown sync type for {remote_url}, skipping peer {peer.name}")
            continue

        try:
            result = subprocess.run(
                command, capture_output=True, text=True, check=True)
            if result.returncode == 0:
                print(f"Successfully cloned {folder} from {peer.name}")
                return  sync_type
        except subprocess.CalledProcessError as e:
            print(f"Failed to clone from peer {peer.name}: {e.stderr}")

    return SyncNodeConfig.SYNC_TYPE_UNKNOWN


def handle_clone_command(folder, peer):
    config = Config.get_local_instance()
    peers = [config.get_peer(peer)] if peer else config.get_peers().values()

    # Check if the folder already exists
    if os.path.exists(folder):
        raise FileExistsError(f"Cannot clone into existing folder: {folder}")

    sync_type = _clone_project(folder, peers)
    if sync_type != SyncNodeConfig.SYNC_TYPE_UNKNOWN:
        SyncNodeConfig.create_default_config(folder, sync_type)
    else:
        print(f"Error: Could not clone {folder} from any peer")


def handle_list_command(folder, remote, peer, cached):
    config = Config.get_local_instance()
    node = _get_root_node(folder)
    if node is None:
        return
    node.scan()
    ours = node.get_children_tree_by_path()
    print(f"Local projects: {ours}")

    if not remote:
        return

    available = {}
    peers = [config.get_peer(peer)] if peer else config.get_peers().values()

    for p in peers:
        remote_projects = list_remote_projects(p, cached)
        filtered = {pth: name for pth,
                    name in remote_projects.items() if pth not in ours}
        available.update(filtered)

    print(f"Available remote projects: {available}")


def list_remote_projects(peer, cached):
    if peer.is_localhost():
        return {}
    return peer.get_remote_projects(cached)


def handle_peers_command(verbose):
    config = Config.get_local_instance()
    path = os.path.abspath(os.path.expanduser(config.projects_path))
    node = NodeFactory.from_folder(path)
    for _, peer in node.config.get_peers().items():
        status = ": is down" if peer.is_down else ""
        print(f"{peer.name}{status}")


if __name__ == "__main__":
    main()
