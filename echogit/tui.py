import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterator

import urwid

from echogit.config import Config
from echogit.node import Node
from echogit.node_factory import from_path
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
    def __init__(self, node: Node, hooks: "UiHooks"):
        self.node = node
        self._hooks = hooks
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
        if not self.node.is_folder and not self.node.state.presence.exists_locally:
            return "remote"
        if self.node.has_error():
            return "error"
        if self.node.sync_state() == "unknown" or not self.node.is_scanned():
            return "unknown"
        return "normal"

    def selectable(self) -> bool:  # pylint: disable=invalid-overridden-method
        return True

    def toggle_expand(self):
        self.node.state.presence.collapse = not self.node.state.presence.collapse
        if not self.node.state.presence.collapse:
            self._hooks.notify(
                status=f"Expanding: {self.node.name}", increment=False, force=True
            )
            self._hooks.set_busy(True)
            threading.Thread(
                target=self._expand_in_background, daemon=True
            ).start()
        self._hooks.refresh(self.node)

    def _expand_in_background(self):
        self.node.ensure_scanned(on_update=self._hooks.notify)
        self._hooks.set_busy(False)
        self._hooks.notify(status="Ready", increment=False, force=True)

    def update_display(self):
        indent = "  " * self.node.depth
        prefix = f"{indent}|- " if self.node.depth else ""
        self.name_widget.set_text(f"{prefix}{self.node.get_icon()} {self.node.name}")
        node_state, attr = self._status_for_node()
        self.status.set_text(node_state)
        self._attr_map.set_attr_map({None: attr})

    def _status_for_node(self) -> tuple[str, str]:
        state = "OK"
        attr = "normal"
        if self.node.has_error() or self.node.sync_state() == "error":
            state, attr = "ERR", "error"
        elif not self.node.is_folder and not self.node.state.presence.exists_locally:
            state, attr = "REMOTE", "remote"
        elif not self.node.is_scanned():
            state, attr = "UNK", "unknown"
        elif self.node.sync_state() == "ok":
            if self.node.is_dirty():
                state, attr = "STALE", "stale"
            else:
                state, attr = "SYNCED", "normal"
        elif self.node.is_dirty():
            state, attr = "DIRTY", "normal"
        elif self.node.sync_state() == "unknown":
            state, attr = "SYNC?", "unknown"
        return state, attr

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
                self._hooks.refresh()
        elif key.lower() == "r":
            self._hooks.notify(
                status=f"Syncing: {self.node.name}", increment=False, force=True
            )
            self._hooks.set_busy(True)
            threading.Thread(
                target=self._sync_in_background, daemon=True
            ).start()
            self._hooks.refresh()
        else:
            return key
        return None

    def _sync_in_background(self):
        self.node.ensure_scanned_deep(on_update=self._hooks.notify)
        self.node.begin_sync()
        self._sync_counts = {"projects": 0, "branches": 0}
        self.node.sync(on_progress=self._on_sync_progress)
        self._hooks.set_busy(False)
        self._hooks.notify(status="Ready", increment=False, force=True)

    def _on_sync_progress(self, node: Node, _success: bool) -> None:
        if isinstance(node, ProjectNode):
            self._sync_counts["projects"] += 1
        elif isinstance(node, BranchNode):
            self._sync_counts["branches"] += 1
        self._hooks.notify(
            status=(
                f"Syncing: {self._sync_counts['projects']} projects, "
                f"{self._sync_counts['branches']} branches"
            ),
            increment=False,
            force=True,
        )

    def show_logs(self):
        log_text = urwid.Text("\n".join(self.node.state.log.lines))
        log_overlay = urwid.Overlay(
            urwid.LineBox(urwid.Filler(log_text, valign="top")),
            urwid.SolidFill(" "),
            align="center",
            width=("relative", 80),
            valign="middle",
            height=("relative", 80),
        )

        prev_handler = self._hooks.loop.unhandled_input
        prev_widget = self._hooks.loop.widget

        def exit_logs(key):
            if isinstance(key, str) and key.lower() in ("q", "esc"):
                self._hooks.loop.widget = prev_widget
                self._hooks.loop.unhandled_input = prev_handler

        self._hooks.loop.widget = log_overlay
        self._hooks.loop.unhandled_input = exit_logs


@dataclass(frozen=True)
class UiHooks:
    refresh: Callable[[Node | None], None]
    loop: urwid.MainLoop
    notify: Callable[..., None]
    set_busy: Callable[[bool], None]


@dataclass
class _SpinnerState:
    frames: str = "|/-\\"
    idx: int = 0


@dataclass
class _UiState:
    scanning: bool = True
    busy: bool = False
    notify_fd: int | None = None
    last_notify: float = 0.0
    found_count: int = 0
    status_label: str = "Scanning projects..."
    spinner: _SpinnerState = field(default_factory=_SpinnerState)

@dataclass
class _UiView:
    status_widget: urwid.Text
    walker: urwid.SimpleFocusListWalker
    widgets: Dict[Node, ProjectWidget]


class TUI:
    def __init__(self, root: Node, *, sync_on_start: bool = False):
        self.root = root
        self.sync_on_start = sync_on_start
        status_widget = urwid.Text("Scanning projects...")
        self._view = _UiView(
            status_widget=status_widget,
            walker=urwid.SimpleFocusListWalker([status_widget]),
            widgets={},
        )
        self.loop: urwid.MainLoop | None = None
        self._state = _UiState()

    def iter_visible_nodes(self, node: Node) -> Iterator[Node]:
        yield node
        if not node.state.presence.collapse:
            for child in list(node.children):
                yield from self.iter_visible_nodes(child)

    def refresh(self, selected_node: Node | None = None):
        self._view.walker.clear()
        if self._state.scanning or self._state.busy:
            self._view.walker.append(self._view.status_widget)
        for node in self.iter_visible_nodes(self.root):
            hooks = UiHooks(
                refresh=self.refresh,
                loop=self.loop,
                notify=self._notify_progress,
                set_busy=self._set_busy,
            )
            widget = self._view.widgets.setdefault(
                node,
                ProjectWidget(node, hooks),
            )
            widget.update_display()
            self._view.walker.append(widget)

        if selected_node:
            for idx, widget in enumerate(self._view.walker):
                if isinstance(widget, ProjectWidget) and widget.node is selected_node:
                    self._view.walker.set_focus(idx)
                    break

    def run(self):
        listbox = urwid.ListBox(self._view.walker)
        self.loop = urwid.MainLoop(listbox, PALETTE, screen=SafeScreen())
        self.refresh()
        self._state.notify_fd = self.loop.watch_pipe(self._on_background_notify)
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
        self._state.scanning = False
        self._notify_progress(force=True, increment=False)

    def _notify_progress(
        self,
        force: bool = False,
        increment: bool = True,
        status: str | None = None,
        node: Node | None = None,
    ) -> None:
        if increment and isinstance(node, ProjectNode):
            self._state.found_count += 1
        if status is not None:
            self._state.status_label = status
        now = time.monotonic()
        if not force and now - self._state.last_notify < 0.2:
            return
        self._state.last_notify = now
        if self._state.notify_fd is not None:
            try:
                os.write(self._state.notify_fd, b"p")
            except OSError:
                self._state.notify_fd = None

    def _on_background_notify(self, _data: bytes) -> bool:
        self.refresh()
        return True

    def _tick_status(self, _loop, _user_data):
        if not self._state.scanning and not self._state.busy:
            self.loop.set_alarm_in(0.1, self._tick_status)
            return
        self._state.spinner.idx = (
            self._state.spinner.idx + 1
        ) % len(self._state.spinner.frames)
        spin = self._state.spinner.frames[self._state.spinner.idx]
        self._view.status_widget.set_text(
            f"{spin} {self._state.status_label} ({self._state.found_count} found)"
        )
        self.loop.set_alarm_in(0.1, self._tick_status)

    def _set_busy(self, value: bool) -> None:
        self._state.busy = value


def run_ui(root_folder: Path, config: Config):
    root_node = from_path(root_folder, config=config)
    root_node.state.presence.collapse = False
    tui = TUI(root_node)
    tui.run()


class SafeScreen(urwid.raw_display.Screen):  # pylint: disable=too-few-public-methods
    def get_cols_rows(self):
        try:
            return super().get_cols_rows()
        except SystemError:
            try:
                size = os.get_terminal_size(self._term_output_file.fileno())
                return size.columns, size.lines
            except OSError:
                return 80, 24
