import os
import threading
import time
from pathlib import Path
from typing import Dict, Iterator

import urwid

from echogit.config import Config
from echogit.node import Node
from echogit.sync.branch_node import BranchNode
from echogit.sync.project_node import ProjectNode

PALETTE = [
    ("reversed", "standout", ""),
    ("highlighted", "black", "light green", "bold"),
    ("error", "light red", ""),
    ("normal", "light green", ""),
    ("remote", "light blue", ""),
    ("unknown", "yellow", ""),
    ("stale", "yellow", ""),
]


class ProjectWidget(urwid.WidgetWrap):
    def __init__(self, node: Node, refresh, loop, notify, set_busy):
        self.node = node
        self._refresh_ui = refresh
        self._loop_ui = loop
        self._notify_ui = notify
        self._set_busy = set_busy
        self._sync_counts = {"projects": 0, "branches": 0}

        self.name_widget = urwid.Text("")
        self.status = urwid.Text("", wrap="clip")

        content = urwid.Columns(
            [
                ("fixed", 8, urwid.AttrMap(self.status, None)),
                ("weight", 1, self.name_widget),
            ]
        )

        self._attr_map = urwid.AttrMap(
            content, self._select_row_attr(), focus_map="reversed"
        )
        super().__init__(self._attr_map)

    def _select_row_attr(self) -> str:
        if not self.node.is_folder and not self.node.exists_locally:
            return "remote"
        if self.node.has_error():
            return "error"
        if self.node.sync_state() == "unknown" or not self.node.is_scanned():
            return "unknown"
        return "normal"

    def selectable(self) -> bool:
        return True

    def toggle_expand(self):
        self.node.toggle_collapse()
        if not self.node.get_collapse():
            self._notify_ui(
                status=f"Expanding: {self.node.name}", increment=False, force=True
            )
            self._set_busy(True)
            threading.Thread(
                target=self._expand_in_background, daemon=True
            ).start()
        self._refresh_ui(self.node)

    def _expand_in_background(self):
        self.node.ensure_scanned(on_update=self._notify_ui)
        self._set_busy(False)
        self._notify_ui(status="Ready", increment=False, force=True)

    def update_display(self):
        indent = "  " * self.node.depth
        prefix = f"{indent}|- " if self.node.depth else ""
        self.name_widget.set_text(f"{prefix}{self.node.get_icon()} {self.node.name}")
        node_state, attr = self._status_for_node()
        self.status.set_text(node_state)
        self._attr_map.set_attr_map({None: attr})

    def _status_for_node(self) -> tuple[str, str]:
        if self.node.has_error() or self.node.sync_state() == "error":
            return "ERR", "error"
        if not self.node.is_folder and not self.node.exists_locally:
            return "REMOTE", "remote"
        if not self.node.is_scanned():
            return "UNK", "unknown"
        if self.node.sync_state() == "ok":
            return ("STALE", "stale") if self.node.is_dirty() else ("SYNCED", "normal")
        if self.node.is_dirty():
            return "DIRTY", "normal"
        if self.node.sync_state() == "unknown":
            return "SYNC?", "unknown"
        return "OK", "normal"

    def keypress(self, _, key):
        if key in ("enter", " "):
            self.toggle_expand()
        elif key.lower() == "l":
            self.show_logs()
        elif key.lower() == "q":
            raise urwid.ExitMainLoop()
        elif key.lower() == "c" and not self.node.is_folder:
            if self.node.clone():
                self.node.scan()
                self._refresh_ui()
        elif key.lower() == "r":
            self._notify_ui(
                status=f"Syncing: {self.node.name}", increment=False, force=True
            )
            self._set_busy(True)
            threading.Thread(
                target=self._sync_in_background, daemon=True
            ).start()
            self._refresh_ui()
        else:
            return key

    def _sync_in_background(self):
        self.node.ensure_scanned_deep(on_update=self._notify_ui)
        self.node.begin_sync()
        self._sync_counts = {"projects": 0, "branches": 0}
        self.node.sync(on_progress=self._on_sync_progress)
        self._set_busy(False)
        self._notify_ui(status="Ready", increment=False, force=True)

    def _on_sync_progress(self, node: Node, _success: bool) -> None:
        if isinstance(node, ProjectNode):
            self._sync_counts["projects"] += 1
        elif isinstance(node, BranchNode):
            self._sync_counts["branches"] += 1
        self._notify_ui(
            status=(
                f"Syncing: {self._sync_counts['projects']} projects, "
                f"{self._sync_counts['branches']} branches"
            ),
            increment=False,
            force=True,
        )

    def show_logs(self):
        log_text = urwid.Text(self.node.get_logs())
        log_overlay = urwid.Overlay(
            urwid.LineBox(urwid.Filler(log_text, valign="top")),
            urwid.SolidFill(" "),
            align="center",
            width=("relative", 80),
            valign="middle",
            height=("relative", 80),
        )

        prev_handler = self._loop_ui.unhandled_input
        prev_widget = self._loop_ui.widget

        def exit_logs(key):
            if isinstance(key, str) and key.lower() in ("q", "esc"):
                self._loop_ui.widget = prev_widget
                self._loop_ui.unhandled_input = prev_handler

        self._loop_ui.widget = log_overlay
        self._loop_ui.unhandled_input = exit_logs


class TUI:
    def __init__(self, root: Node, *, sync_on_start: bool = False):
        self.root = root
        self.sync_on_start = sync_on_start
        self.status_widget = urwid.Text("Scanning projects...")
        self.walker = urwid.SimpleFocusListWalker([self.status_widget])
        self.widgets: Dict[Node, ProjectWidget] = {}
        self.scanning = True
        self.busy = False
        self._notify_fd: int | None = None
        self._last_notify = 0.0
        self._found_count = 0
        self._spinner = "|/-\\"
        self._spinner_idx = 0
        self._status_label = "Scanning projects..."

    def iter_visible_nodes(self, node: Node) -> Iterator[Node]:
        yield node
        if not node.get_collapse():
            for child in list(node.children):
                yield from self.iter_visible_nodes(child)

    def refresh(self, selected_node: Node | None = None):
        self.walker.clear()
        if self.scanning or self.busy:
            self.walker.append(self.status_widget)
        for node in self.iter_visible_nodes(self.root):
            widget = self.widgets.setdefault(
                node,
                ProjectWidget(
                    node,
                    refresh=self.refresh,
                    loop=self.loop,
                    notify=self._notify_progress,
                    set_busy=self._set_busy,
                ),
            )
            widget.update_display()
            self.walker.append(widget)

        if selected_node:
            for idx, widget in enumerate(self.walker):
                if isinstance(widget, ProjectWidget) and widget.node is selected_node:
                    self.walker.set_focus(idx)
                    break

    def run(self):
        listbox = urwid.ListBox(self.walker)
        self.loop = urwid.MainLoop(listbox, PALETTE, screen=SafeScreen())
        self.refresh()
        self._notify_fd = self.loop.watch_pipe(self._on_background_notify)
        self.loop.set_alarm_in(0.1, self._tick_status)
        thread = threading.Thread(
            target=self._scan_and_sync, daemon=True
        )
        thread.start()
        self.loop.run()

    def _scan_and_sync(self) -> None:
        self.root.scan(on_update=self._notify_progress)
        if self.sync_on_start:
            self.root.sync()
        self.scanning = False
        self._notify_progress(force=True, increment=False)

    def _notify_progress(
        self,
        force: bool = False,
        increment: bool = True,
        status: str | None = None,
        node: Node | None = None,
    ) -> None:
        if increment and isinstance(node, ProjectNode):
            self._found_count += 1
        if status is not None:
            self._status_label = status
        now = time.monotonic()
        if not force and now - self._last_notify < 0.2:
            return
        self._last_notify = now
        if self._notify_fd is not None:
            try:
                os.write(self._notify_fd, b"p")
            except OSError:
                self._notify_fd = None

    def _on_background_notify(self, _data: bytes) -> bool:
        self.refresh()
        return True

    def _tick_status(self, _loop, _user_data):
        if not self.scanning and not self.busy:
            self.loop.set_alarm_in(0.1, self._tick_status)
            return
        self._spinner_idx = (self._spinner_idx + 1) % len(self._spinner)
        spin = self._spinner[self._spinner_idx]
        self.status_widget.set_text(
            f"{spin} {self._status_label} ({self._found_count} found)"
        )
        self.loop.set_alarm_in(0.1, self._tick_status)

    def _set_busy(self, value: bool) -> None:
        self.busy = value


def run_ui(root_folder: Path, config: Config):
    from echogit.node_factory import from_path

    root_node = from_path(root_folder, config=config)
    root_node.collapse = False
    tui = TUI(root_node)
    tui.run()


class SafeScreen(urwid.raw_display.Screen):
    def get_cols_rows(self):
        try:
            return super().get_cols_rows()
        except SystemError:
            try:
                size = os.get_terminal_size(self._term_output_file.fileno())
                return size.columns, size.lines
            except OSError:
                return 80, 24
