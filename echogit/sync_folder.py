import subprocess
import argparse
import os
from echogit.git_project import GitProject
from echogit.rsync_project import RsyncProject
from echogit.bare_git_repo import BareGitRepo
from echogit.bare_rsync_repo import BareRsyncRepo
from echogit.node import Node
from echogit.config import Config


class SyncFolder(Node):
    def __init__(self, path, *, config=None, parent=None):
        _path = self._get_folder_name(path)
        super().__init__(_path, path=path, parent=parent, config=config)

    def get_type(self):
        return Node.NodeType.SYNC_FOLDER

    def is_folder(self):
        return True

    def scan(self):
        conf = self.config
        for item in os.listdir(self.path):
            child = None
            full_path = os.path.join(self.path, item)

            node_type = Node.get_type_from_folder(full_path)

            if node_type == Node.NodeType.GIT_PROJECT:
                child = GitProject(full_path, config=conf, parent=self)
            elif node_type == Node.NodeType.RSYNC_PROJECT:
                child = RsyncProject(full_path, config=conf, parent=self)
            elif node_type == Node.NodeType.BARE_GIT_REPO:
                child = BareGitRepo(full_path, config=conf, parent=self)
            elif node_type == Node.NodeType.BARE_RSYNC_REPO:
                child = BareRsyncRepo(full_path, config=conf, parent=self)
            elif node_type == Node.NodeType.SYNC_FOLDER:
                child = SyncFolder(full_path, config=conf, parent=self)
            else:
                continue

            if child:
                child.scan()
                if child.is_folder() and not child.children:
                    continue
                self.add_child(child)

    def sync(self, verbose=False):
        success, total = 0, 0
        # for child_success, child_total in (child.sync(verbose=verbose) for child in self.children):
        for child in self.children:
            child_success, child_total = child.sync(
                verbose=verbose)
            success += child_success
            total += child_total
        return success, total

    def print(self):
        for child in self.children:
            child.print()

    def _create_echogit_config(self, echogit_path):
        config = configparser.ConfigParser()
        config['BRANCHES'] = {
            'sync_branches': 'master, dev, echogit-master, echogit-dev',
            'sync_remotes': 'orion',
        }
        with open(os.path.join(echogit_path, 'config.ini'), 'w') as configfile:
            config.write(configfile)

    def add_project(self, project_name, additional_repo=None):
        git_repo_path = os.path.join(
            self.config.git_path.rstrip('/'), f"{project_name}.git")
        data_repo_path = os.path.join(self.config.projects_path, project_name)

        if os.path.exists(data_repo_path):
            print(f"SyncFolder '{project_name}' already exists.")
            return

        if not self._can_create_echogit_repository(data_repo_path):
            print(f"Cannot create project here: '{data_repo_path}'.")
            return

        if os.path.exists(git_repo_path):
            user_input = input(
                f"Git repository '{git_repo_path}' already exists. Use it? [Y/n] ").strip().lower()
            if user_input not in ['y', '']:
                print("Operation cancelled.")
                return
        else:
            os.makedirs(git_repo_path, exist_ok=True)
            subprocess.run(["git", "init", "--bare"], cwd=git_repo_path)

        os.makedirs(data_repo_path, exist_ok=True)
        subprocess.run(["git", "init"], cwd=data_repo_path)
        subprocess.run(["git", "remote", "add", "origin",
                       git_repo_path], cwd=data_repo_path)

        if additional_repo:
            remote_name, remote_url = additional_repo
            subprocess.run(["git", "remote", "add", remote_name,
                           remote_url], cwd=data_repo_path)

        echogit_path = os.path.join(data_repo_path, ".echogit")
        os.makedirs(echogit_path, exist_ok=True)
        self._create_echogit_config(echogit_path)

        print(f"Project '{project_name}' added.")

    def execute_command(self, command, project_name, additional_repo=None):
        if command == "list":
            self.print()
        elif command == "add" and project_name:
            self.add_project(project_name, additional_repo)
        elif command == "sync":
            self.sync(True)
        else:
            print("Invalid command or missing project name.")

    def get_children_tree_by_path(self):
        tree = {}
        for child in self.children:
            child_tree = child.get_children_tree_by_path()
            tree.update(child_tree)
        return tree


if __name__ == "__main__":
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Synchronize a Git branch with a remote repository")
    parser.add_argument("path", type=str,
                        help="The local path to the Git project")

    # Parse arguments from command line
    args = parser.parse_args()

    config = Config()
    folder = SyncFolder(args.path, config=config)
    folder.scan()
    folder.sync()
