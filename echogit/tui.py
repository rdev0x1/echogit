import urwid
from projects import Projects
from config import Config
from peers import Peers

class ProjectWidget(urwid.WidgetWrap):
    FILE_ICON = "📄"
    FOLDER_CLOSED_ICON = "📁"
    FOLDER_OPEN_ICON = "📂"

    def __init__(self, node, list_walker, depth):
        self.project_name = node.get_name()
        self.is_folder = node.is_folder
        self.is_expanded = True
        self.list_walker = list_walker
        self.children_widgets = []
        self.status_details = node.get_status()
        self.depth = depth
        self.logs = node.get_logs()

        self.icon = self.FOLDER_OPEN_ICON if self.is_folder else self.FILE_ICON
        self.header = urwid.Text(self._get_header_text())
        self.status = urwid.Text(self.status_details, wrap='clip')
        status_attr = 'error' if node.has_error() else 'normal'
        status_widget = urwid.AttrMap(self.status, status_attr)

        content = urwid.Columns([
            ('weight', 2, self.header),
            ('weight', 10, status_widget)
        ])

        self.item = content
        content.original_widget = self
        super().__init__(urwid.AttrMap(self.item, None, focus_map='reversed'))

    def _get_header_text(self):
        prefix = "  " * (self.depth - 1) + "|-" if self.depth > 0 else ""
        return f"{prefix}{self.icon} {self.project_name}"

    def selectable(self):
        return True

    def collapse_widget(self, widget):
        widget.is_expanded = False
        if widget.is_folder:
            widget.icon = self.FOLDER_CLOSED_ICON
        widget.update_display()
        for child in widget.children_widgets:
            if child.item.original_widget in widget.list_walker:
                widget.list_walker.remove(child.item.original_widget)
            if child.item.original_widget.is_folder == True:
                self.collapse_widget(child.item.original_widget)

    def toggle_expand(self):
        my_widget = self.item.original_widget
        if my_widget not in self.list_walker:
            print(f"Error: Widget '{self.project_name}' id={id(self.item)} not found in the list!")
            return

        self.is_expanded = not self.is_expanded

        if self.is_expanded:
            if self.is_folder:
                self.icon = self.FOLDER_OPEN_ICON
            index = self.list_walker.index(my_widget)
            for child in reversed(self.children_widgets):
                if child.item.original_widget not in self.list_walker:
                    self.list_walker.insert(index + 1, child.item.original_widget)
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
            # Folder have no logs
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
    widget = ProjectWidget(node, list_walker, depth)
    list_walker.append(widget)
    if parent_widget:
        parent_widget.add_child(widget)
    if node.is_folder:
        for project in node.children:
            build_ui_project(project, list_walker, parent_widget=widget, depth=depth+1)

def build_ui(root):
    """
    Construct the UI for the application using the root folder containing all projects.
    """
    list_walker = urwid.SimpleFocusListWalker([])
    build_ui_project(root, list_walker)
    return urwid.ListBox(list_walker)

def main():
    global main_loop
    config = Config()
    peers = Peers(config)
    projects = Projects(config, peers)
    root = projects.sync_projects(verbose=False)

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
    main()
