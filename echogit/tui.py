from pathlib import Path
from typing import Dict, Iterator

import urwid

from echogit.config import Config
from echogit.node import Node

PALETTE = [
    ("reversed", "standout", ""),
    ("highlighted", "black", "light green", "bold"),
    ("error", "light red", ""),
    ("normal", "light green", ""),
    ("remote", "light blue", ""),
]


class ProjectWidget(urwid.WidgetWrap):
    def __init__(self, node: Node, refresh, loop):
        self.node = node
        self._refresh_ui = refresh
        self._loop_ui = loop

        self.name_widget = urwid.Text("")
        self.status = urwid.Text("", wrap="clip")

        content = urwid.Columns(
            [
                ("fixed", 8, urwid.AttrMap(self.status, None)),
                ("weight", 1, self.name_widget),
            ]
        )

        super().__init__(
            urwid.AttrMap(content, self._select_row_attr(), focus_map="reversed")
        )

    def _select_row_attr(self) -> str:
        if not self.node.is_folder and not self.node.exists_locally:
            return "remote"
        if self.node.has_error():
            return "error"
        return "normal"

    def selectable(self) -> bool:
        return True

    def toggle_expand(self):
        self.node.toggle_collapse()
        self._refresh_ui(self.node)

    def update_display(self):
        indent = "  " * self.node.depth
        prefix = f"{indent}|- " if self.node.depth else ""
        self.name_widget.set_text(f"{prefix}{self.node.get_icon()} {self.node.name}")
        node_state = "ERR" if self.node.has_error() else "OK"
        self.status.set_text(node_state)

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
            self.node.scan()
            self.node.sync()
            self._refresh_ui()
        else:
            return key

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
            if key.lower() in ("q", "esc"):
                self._loop_ui.widget = prev_widget
                self._loop_ui.unhandled_input = prev_handler

        self._loop_ui.widget = log_overlay
        self._loop_ui.unhandled_input = exit_logs


class TUI:
    def __init__(self, root: Node):
        self.root = root
        self.root.scan()
        self.root.sync()
        self.walker = urwid.SimpleFocusListWalker([])
        self.widgets: Dict[Node, ProjectWidget] = {}

    def iter_visible_nodes(self, node: Node) -> Iterator[Node]:
        yield node
        if not node.get_collapse():
            for child in node.children:
                yield from self.iter_visible_nodes(child)

    def refresh(self, selected_node: Node | None = None):
        self.walker.clear()
        for node in self.iter_visible_nodes(self.root):
            widget = self.widgets.setdefault(
                node, ProjectWidget(node, refresh=self.refresh, loop=self.loop)
            )
            widget.update_display()
            self.walker.append(widget)

        if selected_node:
            for idx, widget in enumerate(self.walker):
                if widget.node is selected_node:
                    self.walker.set_focus(idx)
                    break

    def run(self):
        listbox = urwid.ListBox(self.walker)
        self.loop = urwid.MainLoop(listbox, PALETTE)
        self.refresh()
        self.loop.run()


def run_ui(root_folder: Path, config: Config):
    from echogit.node_factory import from_path

    root_node = from_path(root_folder, config=config)
    root_node.collapse = False
    tui = TUI(root_node)
    tui.run()
