# echogit Architecture and objects

`echogit` is a command-line application that synchronizes folders with Git or Rsync. Below is an overview of the architecture:

echogit/
├── __main__.py   # CLI entry
├── config.py     # single, simple config class
├── node.py       # node class
├── sync/
│   ├── git_sync.py   # encapsulate git syncing logic
│   └── rsync_sync.py # encapsulate rsync logic
├── discovery.py  # discovery logic (local & remote)
├── tui.py        # unchanged, keep as-is
└── utils.py      # helpers (ssh, subprocess helpers)
|__plugin/
         ├── loader.py 
         └── bus.py

## Flag used on TUI

- OK : no error
- D: dirty
- P: push issue
- L: pull issue
- R: remote issue
