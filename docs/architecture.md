# echogit Architecture and objects

`echogit` is a command-line application that synchronizes folders with Git or Rsync. Below is an overview of the architecture:

## Node
An abstract class that serves as the base for all project-related objects.

## Types of Folders

### SyncFolder
A folder that may contain `GitSyncProject`, `RsyncSyncProject`, or other `SyncFolder` instances. Syncing a `SyncFolder` involves syncing its contents.

### GitSyncProject
Represents a folder containing a Git project with an `echogit` configuration. This folder is synchronized using Git.

### RsyncSyncProject
Represents a folder containing an `echogit` configuration and is synchronized using Rsync.

### BareGitRepo
Represents a bare Git repository (ending with `.git`) where content cannot be manually updated. Sync is done via Git.

### BareRsyncRepo
Represents a bare Rsync repository (ending with `.rsync`). Content cannot be manually updated.

## Git Repository Components

### SyncRepository
A repository within a `GitSyncProject` that contains one or more branches. It links to a `Peer` for synchronization.

### SyncBranch
Represents a branch of a `SyncRepository` that is synchronized with remote peers.

## Peer Configuration

### Peer
Contains IP and other data required to configure remotes for both Git and Rsync synchronization.

### Config
Holds the main and peer configurations. Peers are linked to this object.

### SyncNodeConfig
Holds configuration data specific to synchronization, such as which protocol and branches to sync.

## Flag used on TUI

- OK : no error
- D: dirty
- P: push issue
- L: pull issue
- R: remote issue
