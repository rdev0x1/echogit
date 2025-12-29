# Quickstart

## Configure

Create `~/.config/echogit/config.ini` and set the key paths:

```ini
[DEFAULT]
projects_path = ~/echogit/projects
git_path = ~/echogit/git

[PEERS]
peers = mylaptop, myserver
```

Optional per-peer path rules:

```ini
[mylaptop]
allowed_paths = notes, music
```

Optional auto-commit list (relative to `projects_path`):

```ini
[AUTOCOMMIT]
projects = notes, contacts
```

## Discover projects

List local projects:

```bash
echogit list
```

List remote projects (all peers):

```bash
echogit list-remote
```

JSON output for echogit-mobile or scripts:

```bash
echogit list --json
echogit list-remote --json
```

## Sync

Sync all projects under `projects_path`:

```bash
echogit sync
```

Sync a specific folder:

```bash
echogit sync /path/to/projects
```

Show progress output:

```bash
echogit sync --progress
echogit sync --progress --status
```

## TUI

```bash
echogit tui
```

Controls:

- `enter` / `space`: expand or collapse folders
- `r`: scan + sync the selected node (recursively), then push
- `l`: show logs for the selected node
- `q`: quit

## Config helpers

Get global config values:

```bash
echogit config -g
```

Set global config values:

```bash
echogit config -s "projects_path=/path/to/data"
```

Get per-project auto-commit:

```bash
echogit config /path/to/project -g
```

Set per-project auto-commit:

```bash
echogit config /path/to/project -s "autoCommit:true"
```
