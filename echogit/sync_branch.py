import os
import subprocess
import argparse
from echogit.node import Node
from echogit.config import Config
from echogit.peer import Peer
from echogit.status_cache import StatusCache


class SyncBranch(Node):
    def __init__(self, branch_name, *, path, peer, config=None, parent=None):
        super().__init__(branch_name, path=path, config=config, parent=parent)
        self.cache = StatusCache(path)
        if self.cache.load_status():
            self.stderr = self.cache.stderr
            self.stdout = self.cache.stdout
            self.errors = self.cache.errors
        else:
            self.errors = {"remote_add": 0, "push": 0, "pull": 0, "status": 0}
            self.stderr = {"remote_add": "",
                           "push": "", "pull": "", "status": ""}
            self.stdout = {"remote_add": "",
                           "push": "", "pull": "", "status": ""}

        self.peer = peer

    def get_errors(self):
        return self.errors

    # Nothing to do
    def scan(self):
        pass

    def _save_result_logs(self, key, result, verbose):
        self.errors[key] = int(result.returncode)
        self.stderr[key] = result.stderr
        self.stdout[key] = result.stdout

        if verbose:
            print(f"ret={result.returncode} stdout={result.stdout} \
            stderr={result.stderr}")

    def _get_peer_url(self):
        return self.peer.get_remote_project_url(self.path)

    def _add_remote(self, verbose):
        git_path = self._get_peer_url()

        # Get existing remotes
        result = subprocess.run(["git", "remote", "get-url", self.peer.name],
                                cwd=self.path, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE)
        remote_url = result.stdout.decode("utf-8").strip()

        if result.returncode == 0:  # Remote exists
            if remote_url == git_path:
                if verbose:
                    print(f"Remote '{self.peer.name}' already exists.")
            else:
                if verbose:
                    print(f"Remote {self.peer.name} => {git_path}")
                result = subprocess.run(["git", "remote", "set-url",
                                         self.peer.name, git_path],
                                        cwd=self.path)
        else:
            if verbose:
                print(f"Adding remote {self.peer.name} = {git_path}")
            result = subprocess.run(["git", "remote", "add", self.peer.name,
                                     git_path], cwd=self.path)

        self._save_result_logs("remote_add", result, verbose)

    def _push(self, verbose):
        branch = self.name
        result = subprocess.run(["git", "push", self.peer.name, branch],
                                cwd=self.path, text=True, capture_output=True)
        self._save_result_logs("push", result, verbose)

    def _pull(self, verbose):
        branch = self.name
        result = subprocess.run(["git", "pull", self.peer.name, branch],
                                cwd=self.path, text=True, capture_output=True)
        self._save_result_logs("pull", result, verbose)

    def _fetch(self):
        subprocess.run(["git", "fetch", self.peer.name], cwd=self.path)

    def _status(self, verbose=False):
        result = subprocess.run(["git", "status", "--porcelain"],
                                cwd=self.path, text=True, capture_output=True)
        self._save_result_logs("status", result, verbose)
        if (result.returncode == 0) and (bool(result.stdout)):
            result.returncode = 10  # FIXME
        self._save_result_logs("status", result, verbose)
        return result.returncode

    def get_logs(self):
        _str = f"branch={self.name}\n"
        for key in ["remote_add", "push", "pull", "status"]:
            _str += f"-----{key} returnCode={self.errors[key]}-----\n"
            _str += f"stdout={self.stdout[key]}\n"
            _str += f"stderr={self.stderr[key]}\n"
        return _str

    def has_error(self):
        for key in ["remote_add", "push", "pull", "status"]:
            if self.errors[key] != 0:
                return True
        return False

    def nb_children(self):
        return len(self.children)

    def _commit(self):
        print("******* commit *****")
        result = subprocess.run(["git", "add", "-A", "."],
                                cwd=self.path, text=True, capture_output=True)
        result = subprocess.run(["git", "commit", "-m", "echogit auto commit"],
                                cwd=self.path, text=True, capture_output=True)

    def _branch(self):
        result = subprocess.run(["git", "branch"], cwd=self.path, text=True,
                                capture_output=True)

    def _branch(self):
        result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"],
                                cwd=self.path, text=True, capture_output=True)

        if result.returncode == 0:
            return result.stdout.strip()  # Current branch name
        else:
            raise Exception(f"Error getting branch: {result.stderr}")

    def _checkout(self, branch):
        current_branch = self._branch()
        if current_branch == branch:
            return current_branch
        subprocess.run(["git", "checkout", branch], cwd=self.path)
        return current_branch

    def sync(self, verbose=False):
        current_branch = self._checkout(self.name)
        self._add_remote(verbose)
        self._fetch()
        if self.node_config.auto_commit and self._status() != 0:
            self._commit()
        self._push(verbose)
        self._pull(verbose)
        self._status(verbose)
        self.cache.cache_status(self.errors, self.stderr,
                                self.stdout, self.peer.is_down)

        # restore branch
        self._checkout(current_branch)
        if self.peer.is_down or self.has_error():
            success = 0
        else:
            success = 1
        return success, 1


if __name__ == "__main__":
    # Setup argument parser
    parser = argparse.ArgumentParser(
        description="Synchronize a Git branch with a remote repository")
    parser.add_argument("branch_name", type=str,
                        help="The name of the branch to synchronize")
    parser.add_argument("path", type=str,
                        help="The local path to the Git project")
    parser.add_argument("remote_name", type=str,
                        help="The name of the remote peer to synchronize with")
    parser.add_argument("remote_host", type=str,
                        help="The name of the remote peer to synchronize with")
    parser.add_argument("remote_git_path", type=str,
                        help="The remote repository path (including .git)")

    # Optional verbose argument
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose output (default: False)")

    # Parse arguments from command line
    args = parser.parse_args()

    config = Config()
    peer = Peer(args.remote_name, args.remote_host,
                args.remote_git_path, config=config)
    br = SyncBranch(args.branch_name, path=args.path, peer=peer, config=config)
    br.scan()
    br.sync(args.verbose)
    br.print()
