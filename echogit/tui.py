import urwid
from echogit.config import Config
from echogit.sync_folder import SyncFolder


class ProjectWidget(urwid.WidgetWrap):
    FILE_ICON = "📄"
    FOLDER_CLOSED_ICON = "📁"
    FOLDER_OPEN_ICON = "📂"

    def __init__(self, node, list_walker, depth=0, collapse_folder=False):
        self.project_name = node.name
        self.is_folder = node.is_folder()
        self.collapse_folder = collapse_folder
        self.list_walker = list_walker
        self.children_widgets = []

        # Get the status details and truncate if necessary
        self.status_details = node.get_project_state_str()

        self.depth = depth
        self.logs = node.get_logs()

        # Set folder or file icon
        if self.collapse_folder:
            folder_icon = self.FOLDER_CLOSED_ICON
        else:
            folder_icon = self.FOLDER_OPEN_ICON

        self.icon = folder_icon if self.is_folder else self.FILE_ICON
        self.header = urwid.Text(self._get_header_text())

        # Create the status text widget and truncate if necessary
        self.status = urwid.Text(self.status_details, wrap='clip')
        status_attr = 'error' if node.has_error() else 'normal'
        status_widget = urwid.AttrMap(self.status, status_attr)

        # Build the content layout
        content = urwid.Columns([
            ('weight', 2, self.header),
            ('weight', 10, status_widget)
        ])

        self.item = content
        content.original_widget = self
        super().__init__(urwid.AttrMap(self.item, None, focus_map='reversed'))

    def _truncate_project_name(self, name, max_length):
        """Truncate the status details if they exceed the maximum length."""
        if len(name) > max_length:
            # Reserve 3 characters for "..."
            return name[:max_length - 3] + "..."
        return name

    def _get_header_text(self):
        project = self._truncate_project_name(self.project_name, 10)
        prefix = "  " * (self.depth - 1) + "|-" if self.depth > 0 else ""
        return f"{prefix}{self.icon} {project}"

    def selectable(self):
        return True

    def collapse_widget(self, widget):
        widget.collapse_folder = True
        if widget.is_folder:
            widget.icon = self.FOLDER_CLOSED_ICON
        widget.update_display()
        for child in widget.children_widgets:
            if child.item.original_widget in widget.list_walker:
                widget.list_walker.remove(child.item.original_widget)
            if child.item.original_widget.is_folder:
                self.collapse_widget(child.item.original_widget)

    def toggle_expand(self):
        my_widget = self.item.original_widget
        if my_widget not in self.list_walker:
            print(
                f"Error: Widget '{self.project_name}' id={id(self.item)} not found in the list!")
            return

        self.collapse_folder = not self.collapse_folder

        if not self.collapse_folder:
            if self.is_folder:
                self.icon = self.FOLDER_OPEN_ICON
            index = self.list_walker.index(my_widget)
            for child in reversed(self.children_widgets):
                if child.item.original_widget not in self.list_walker:
                    self.list_walker.insert(
                        index + 1, child.item.original_widget)
        else:
            if self.is_folder:
                self.icon = self.FOLDER_CLOSED_ICON
            self.collapse_widget(self)

        self.update_display()

    def update_display(self):
        self.header.set_text(self._get_header_text())
        self.status.set_text(self.status_details)

    def add_child(self, widget):
        self.children_widgets.append(widget)

    def keypress(self, size, key):
        if key in ('enter', ' '):
            self.toggle_expand()
            return None
        if key in ('l', 'L'):
            # SyncFolder have no logs
            if self.is_folder:
                return None
            self.show_logs()
            return None

        return key

    def show_logs(self):
        log_text = urwid.Text(self.logs)
        log_fill = urwid.Filler(log_text, valign='top')
        log_box = urwid.LineBox(log_fill)
        log_overlay = urwid.Overlay(log_box, urwid.SolidFill(' '), align='center', width=('relative', 80),
                                    valign='middle', height=('relative', 80))

        def exit_logs(key):
            if key in ('q', 'Q', 'esc'):
                main_loop.widget = main_widget
                main_loop.unhandled_input = None

        main_widget = main_loop.widget
        main_loop.widget = log_overlay
        main_loop.unhandled_input = exit_logs


def build_ui_project(node, list_walker, parent_widget=None, depth=0):
    """
    Recursively build the UI for each project or folder node.

    :param node: A project or folder node.
    :param list_walker: The list walker to which the UI elements are appended.
    :param parent_widget: The parent ProjectWidget if this is a subproject.
    """
    widget = ProjectWidget(node, list_walker, depth, node.collapse)
    list_walker.append(widget)

    if parent_widget:
        parent_widget.add_child(widget)

    if node.is_folder():
        for project in node.children:
            build_ui_project(project, list_walker, parent_widget=widget,
                             depth=depth+1)

    # Collapse only after all children are added
    if node.collapse:
        widget.collapse_widget(widget)


def build_ui(root):
    """
    Construct the UI for the application using the root folder containing all projects.
    """
    list_walker = urwid.SimpleFocusListWalker([])
    build_ui_project(root, list_walker)
    return urwid.ListBox(list_walker)


def run_ui():
    global main_loop
    config = Config.get_local_instance()
    root = SyncFolder(config.projects_path, config=config)
    root.scan()
    root.sync()

    palette = [
        ('reversed', 'standout', ''),
        ('highlighted', 'black', 'light green', 'bold'),
        ('error', 'light red', ''),
        ('normal', 'light green', ''),
        ('hidden', 'black', 'black'),
    ]

    listbox = build_ui(root)
    main_loop = urwid.MainLoop(listbox, palette)
    main_loop.run()


if __name__ == "__main__":
    run_ui()
