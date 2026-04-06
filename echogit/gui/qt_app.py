from __future__ import annotations

import sys

from echogit.config import Config
from echogit.core import EchogitService
from echogit.folder_node import FolderNode
from echogit.node import Node
from echogit.sync.branch_node import BranchNode
from echogit.sync.git_sync import GitProjectNode
from echogit.sync.peer_node import PeerNode
from echogit.sync.project_node import ProjectNode
from echogit.sync.rsync_sync import RsyncProjectNode

try:
    from PySide6 import QtCore, QtGui, QtWidgets
except ModuleNotFoundError:
    QtCore = None
    QtGui = None
    QtWidgets = None


def missing_dependency_message() -> str:
    return (
        "The Qt frontend requires PySide6. Install it with "
        "`python -m pip install -e '.[qt]'`."
    )


def main() -> int:
    if QtWidgets is None or QtCore is None or QtGui is None:
        print(missing_dependency_message(), file=sys.stderr)
        return 2

    config = Config.load_from_file()
    service = EchogitService(config)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Echogit")
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(_style_sheet())

    window = MainWindow(service)
    tray = TrayController(app, window)
    tray.show()
    window.show()
    return app.exec()


if QtWidgets is not None and QtCore is not None and QtGui is not None:

    NODE_ROLE = QtCore.Qt.UserRole + 1

    class TreeBuildWorker(QtCore.QObject):
        finished = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(self, service: EchogitService):
            super().__init__()
            self._service = service

        @QtCore.Slot()
        def run(self) -> None:
            try:
                root = self._service.build_tree()
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self.failed.emit(str(exc))
                return
            self.finished.emit(root)


    class NodeLoadWorker(QtCore.QObject):
        finished = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(self, node: Node):
            super().__init__()
            self._node = node

        @QtCore.Slot()
        def run(self) -> None:
            try:
                self._node.ensure_scanned()
                self._node.state.presence.collapse = False
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self.failed.emit(str(exc))
                return
            self.finished.emit(self._node)


    class NodeSyncWorker(QtCore.QObject):
        prepared = QtCore.Signal(int)
        progress = QtCore.Signal(object, bool)
        finished = QtCore.Signal(object, bool)
        failed = QtCore.Signal(str)

        def __init__(self, node: Node):
            super().__init__()
            self._node = node

        @QtCore.Slot()
        def run(self) -> None:
            try:
                self._node.ensure_scanned_deep()
                self.prepared.emit(_sync_progress_total(self._node))
                self._node.begin_sync()
                ok = self._node.sync(on_progress=self._on_progress)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self.failed.emit(str(exc))
                return
            self.finished.emit(self._node, ok)

        def _on_progress(self, node: Node, ok: bool) -> None:
            self.progress.emit(node, ok)


    class NodeTree(QtWidgets.QTreeWidget):
        HEADERS = ["Node", "Kind", "State"]

        def __init__(self):
            super().__init__()
            self.setColumnCount(len(self.HEADERS))
            self.setHeaderLabels(self.HEADERS)
            self.setRootIsDecorated(True)
            self.setAlternatingRowColors(True)
            self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.setIndentation(18)
            self.setAnimated(True)
            self._items_by_node_id: dict[int, QtWidgets.QTreeWidgetItem] = {}

            header = self.header()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

        def set_root(self, root: Node) -> None:
            self.clear()
            self._items_by_node_id.clear()
            root.state.presence.collapse = False
            item = self._append_node(root, None)
            self.expandItem(item)
            self.expandToDepth(1)

        def selected_node(self) -> Node | None:
            item = self.currentItem()
            if item is None:
                return None
            return item.data(0, NODE_ROLE)

        def node_item(self, node: Node) -> QtWidgets.QTreeWidgetItem | None:
            return self._items_by_node_id.get(id(node))

        def refresh_node(self, node: Node) -> None:
            item = self.node_item(node)
            if item is None:
                return
            self._update_item(item, node)
            self._sync_child_items(item, node)

        def refresh_all(self) -> None:
            for item_id, item in list(self._items_by_node_id.items()):
                _ = item_id
                node = item.data(0, NODE_ROLE)
                if node is not None:
                    self._update_item(item, node)

        def load_children(self, item: QtWidgets.QTreeWidgetItem) -> None:
            node = item.data(0, NODE_ROLE)
            if node is None:
                return
            node.state.presence.collapse = False
            self._sync_child_items(item, node)
            self._update_item(item, node)

        def _append_node(
            self,
            node: Node,
            parent_item: QtWidgets.QTreeWidgetItem | None,
        ) -> QtWidgets.QTreeWidgetItem:
            item = QtWidgets.QTreeWidgetItem()
            item.setData(0, NODE_ROLE, node)
            self._update_item(item, node)

            if parent_item is None:
                self.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            self._items_by_node_id[id(node)] = item

            for child in list(node.children):
                self._append_node(child, item)
            if _node_can_expand(node):
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ShowIndicator)
            return item

        def _sync_child_items(
            self,
            item: QtWidgets.QTreeWidgetItem,
            node: Node,
        ) -> None:
            old_children = item.takeChildren()
            for child_item in old_children:
                self._forget_item(child_item)
            for child in list(node.children):
                self._append_node(child, item)
            if _node_can_expand(node):
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.ShowIndicator)
            else:
                item.setChildIndicatorPolicy(QtWidgets.QTreeWidgetItem.DontShowIndicator)

        def _forget_item(self, item: QtWidgets.QTreeWidgetItem) -> None:
            node = item.data(0, NODE_ROLE)
            if node is not None:
                self._items_by_node_id.pop(id(node), None)
            for idx in range(item.childCount()):
                self._forget_item(item.child(idx))

        def _update_item(self, item: QtWidgets.QTreeWidgetItem, node: Node) -> None:
            state = _node_status_text(node)
            item.setText(0, node.name)
            item.setText(1, _node_kind(node))
            item.setText(2, state)
            item.setIcon(0, _node_icon(node))
            item.setIcon(2, _node_status_icon(node))
            item.setForeground(2, _node_status_brush(node))
            item.setToolTip(0, _safe_relative_path(node))
            if node.is_folder:
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#2f3d39")))
            elif not node.state.presence.exists_locally:
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#2c5f86")))
            else:
                item.setForeground(0, QtGui.QBrush(QtGui.QColor("#1f2528")))


    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, service: EchogitService):
            super().__init__()
            self._service = service
            self._root: Node | None = None
            self._thread: QtCore.QThread | None = None
            self._worker: NodeSyncWorker | None = None
            self._scan_thread: QtCore.QThread | None = None
            self._scan_worker: TreeBuildWorker | None = None
            self._load_thread: QtCore.QThread | None = None
            self._load_worker: NodeLoadWorker | None = None
            self._sync_counts = {"projects": 0, "branches": 0}
            self._progress_total = 0
            self._progress_done = 0
            self._busy_cursor_depth = 0
            self.setWindowTitle("Echogit")
            self.resize(1120, 720)

            self.project_tree = NodeTree()
            self.project_tree.currentItemChanged.connect(self._on_selection_changed)
            self.project_tree.itemExpanded.connect(self._on_item_expanded)

            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("No node selected.")

            self.summary_label = QtWidgets.QLabel("")
            self.summary_label.setObjectName("summaryLabel")
            self.activity_label = QtWidgets.QLabel("Ready")
            self.activity_label.setObjectName("activityLabel")
            self.progress_bar = QtWidgets.QProgressBar()
            self.progress_bar.setObjectName("progressBar")
            self.progress_bar.setFixedWidth(190)
            self.progress_bar.setFixedHeight(18)
            self.progress_bar.setTextVisible(False)
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.detail_title = QtWidgets.QLabel("No node selected")
            self.detail_title.setObjectName("detailTitle")
            self.detail_meta = QtWidgets.QLabel("")
            self.detail_meta.setObjectName("detailMeta")
            self.detail_path = QtWidgets.QLabel("")
            self.detail_path.setObjectName("detailPath")
            self.detail_path.setWordWrap(True)

            details = QtWidgets.QFrame()
            details.setObjectName("detailsPanel")
            details_layout = QtWidgets.QVBoxLayout(details)
            details_layout.setContentsMargins(16, 14, 16, 14)
            details_layout.setSpacing(8)
            details_layout.addWidget(self.detail_title)
            details_layout.addWidget(self.detail_meta)
            details_layout.addWidget(self.detail_path)
            details_layout.addStretch(1)

            right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            right_splitter.addWidget(details)
            right_splitter.addWidget(self.log)
            right_splitter.setSizes([190, 390])

            splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            splitter.addWidget(self.project_tree)
            splitter.addWidget(right_splitter)
            splitter.setSizes([680, 420])

            header = QtWidgets.QFrame()
            header.setObjectName("headerBand")
            header_layout = QtWidgets.QHBoxLayout(header)
            header_layout.setContentsMargins(18, 12, 18, 12)
            title = QtWidgets.QLabel("Echogit")
            title.setObjectName("windowTitle")
            header_layout.addWidget(title)
            header_layout.addSpacing(16)
            header_layout.addWidget(self.summary_label)
            header_layout.addStretch(1)
            header_layout.addWidget(self.activity_label)
            header_layout.addWidget(self.progress_bar)

            central = QtWidgets.QWidget()
            central_layout = QtWidgets.QVBoxLayout(central)
            central_layout.setContentsMargins(0, 0, 0, 0)
            central_layout.setSpacing(0)
            central_layout.addWidget(header)
            central_layout.addWidget(splitter, 1)
            self.setCentralWidget(central)

            self.refresh_action = QtGui.QAction("Refresh", self)
            self.refresh_action.setIcon(_theme_icon("view-refresh", "Refresh"))
            self.refresh_action.setToolTip("Refresh tree")
            self.refresh_action.triggered.connect(self.refresh_tree)
            self.sync_action = QtGui.QAction("Sync All", self)
            self.sync_action.setIcon(_theme_icon("emblem-synchronizing", "Sync"))
            self.sync_action.setToolTip("Sync the whole tree")
            self.sync_action.triggered.connect(self.sync_all)
            self.sync_selected_action = QtGui.QAction("Sync Selected", self)
            self.sync_selected_action.setIcon(
                _theme_icon("media-playback-start", "SyncSelected")
            )
            self.sync_selected_action.setToolTip("Sync selected node")
            self.sync_selected_action.triggered.connect(self.sync_selected)
            self.sync_selected_action.setEnabled(False)
            self.quit_action = QtGui.QAction("Quit", self)
            self.quit_action.setIcon(_theme_icon("application-exit", "Quit"))
            self.quit_action.triggered.connect(QtWidgets.QApplication.quit)

            toolbar = QtWidgets.QToolBar("Main")
            toolbar.setMovable(False)
            toolbar.setIconSize(QtCore.QSize(20, 20))
            toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            toolbar.addAction(self.refresh_action)
            toolbar.addAction(self.sync_action)
            toolbar.addAction(self.sync_selected_action)
            self.addToolBar(toolbar)

            self.statusBar().showMessage("Ready")
            self.refresh_tree()

        def refresh_tree(self) -> None:
            if self._is_busy():
                return
            self._set_activity("Scanning tree...")
            self._begin_indeterminate_progress()
            self._set_wait_cursor(True)
            self._scan_thread = QtCore.QThread(self)
            self._scan_worker = TreeBuildWorker(self._service)
            self._scan_worker.moveToThread(self._scan_thread)
            self._scan_thread.started.connect(self._scan_worker.run)
            self._scan_worker.finished.connect(self._on_tree_built)
            self._scan_worker.failed.connect(self._on_tree_build_failed)
            self._scan_worker.finished.connect(self._scan_thread.quit)
            self._scan_worker.failed.connect(self._scan_thread.quit)
            self._scan_thread.finished.connect(self._cleanup_scan_worker)
            self._scan_thread.start()
            self._update_action_state()

        def sync_all(self) -> None:
            if self._root is None:
                self.refresh_tree()
            if self._root is not None:
                self._start_sync(self._root)

        def sync_selected(self) -> None:
            node = self.project_tree.selected_node()
            if node is None:
                return
            self._start_sync(node)

        def _start_sync(self, node: Node) -> None:
            if self._is_busy():
                return
            self._sync_counts = {"projects": 0, "branches": 0}
            self._set_activity(f"Preparing {node.name}...")
            self._begin_indeterminate_progress()
            self._set_wait_cursor(True)

            self._thread = QtCore.QThread(self)
            self._worker = NodeSyncWorker(node)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.prepared.connect(self._on_sync_prepared)
            self._worker.progress.connect(self._on_sync_progress)
            self._worker.finished.connect(self._on_sync_finished)
            self._worker.failed.connect(self._on_sync_failed)
            self._worker.finished.connect(self._thread.quit)
            self._worker.failed.connect(self._thread.quit)
            self._thread.finished.connect(self._cleanup_worker)
            self._thread.start()
            self._update_action_state()

        def _on_item_expanded(self, item) -> None:
            if self._is_busy():
                return
            node = item.data(0, NODE_ROLE)
            if node is None:
                return
            self._set_activity("Loading node...")
            self._begin_indeterminate_progress()
            self._set_wait_cursor(True)
            self._load_thread = QtCore.QThread(self)
            self._load_worker = NodeLoadWorker(node)
            self._load_worker.moveToThread(self._load_thread)
            self._load_thread.started.connect(self._load_worker.run)
            self._load_worker.finished.connect(self._on_node_loaded)
            self._load_worker.failed.connect(self._on_node_load_failed)
            self._load_worker.finished.connect(self._load_thread.quit)
            self._load_worker.failed.connect(self._load_thread.quit)
            self._load_thread.finished.connect(self._cleanup_load_worker)
            self._load_thread.start()
            self._update_action_state()

        def _on_tree_built(self, root: Node) -> None:
            self._root = root
            self.project_tree.set_root(self._root)
            self._set_summary(self._root)
            root_item = self.project_tree.topLevelItem(0)
            if root_item is not None:
                self.project_tree.setCurrentItem(root_item)
            self._set_activity("Ready")

        def _on_tree_build_failed(self, message: str) -> None:
            self._set_activity("Scan failed")
            self.log.setPlainText(f"ERROR: {message}")

        def _cleanup_scan_worker(self) -> None:
            self._scan_worker = None
            self._scan_thread = None
            self._reset_progress()
            self._set_wait_cursor(False)
            self._update_action_state()

        def _on_node_loaded(self, node: Node) -> None:
            item = self.project_tree.node_item(node)
            self.project_tree.refresh_node(node)
            if item is not None:
                item.setExpanded(True)
            self._set_summary(self._root)
            self._refresh_selected_details()
            self._set_activity("Ready")

        def _on_node_load_failed(self, message: str) -> None:
            self._set_activity("Load failed")
            selected = self.project_tree.selected_node()
            if selected is not None:
                selected.log(message, error=True)
                self._show_node_details(selected)
            else:
                self.log.setPlainText(f"ERROR: {message}")

        def _cleanup_load_worker(self) -> None:
            self._load_worker = None
            self._load_thread = None
            self._reset_progress()
            self._set_wait_cursor(False)
            self._update_action_state()

        def _on_sync_prepared(self, total: int) -> None:
            self._progress_total = max(1, total)
            self._progress_done = 0
            self.progress_bar.setRange(0, self._progress_total)
            self.progress_bar.setValue(0)
            self._set_activity(f"Syncing: 0 / {self._progress_total} nodes")

        def _on_sync_progress(self, node: Node, _ok: bool) -> None:
            self._advance_progress()
            if isinstance(node, ProjectNode):
                self._sync_counts["projects"] += 1
            elif isinstance(node, BranchNode):
                self._sync_counts["branches"] += 1
            self.project_tree.refresh_node(node)
            self._refresh_selected_details()
            self._set_activity(
                "Syncing: "
                f"{self._progress_done} / {self._progress_total} nodes, "
                f"{self._sync_counts['projects']} projects, "
                f"{self._sync_counts['branches']} branches"
            )

        def _on_sync_finished(self, node: Node, ok: bool) -> None:
            self.project_tree.refresh_node(node)
            self.project_tree.refresh_all()
            self._set_summary(self._root)
            self._refresh_selected_details()
            self._finish_progress()
            self._set_activity("Sync OK" if ok else "Sync failed")

        def _on_sync_failed(self, message: str) -> None:
            self._finish_progress()
            self._set_activity("Sync failed")
            selected = self.project_tree.selected_node()
            if selected is not None:
                selected.log(message, error=True)
                self._show_node_details(selected)
            else:
                self.log.setPlainText(f"ERROR: {message}")

        def _cleanup_worker(self) -> None:
            self._worker = None
            self._thread = None
            self._set_wait_cursor(False)
            self._update_action_state()

        def _is_busy(self) -> bool:
            return any(
                thread is not None
                for thread in (self._thread, self._scan_thread, self._load_thread)
            )

        def _update_action_state(self) -> None:
            busy = self._is_busy()
            self.sync_action.setEnabled(not busy and self._root is not None)
            self.refresh_action.setEnabled(not busy)
            self.sync_selected_action.setEnabled(
                not busy and self.project_tree.selected_node() is not None
            )

        def _set_activity(self, text: str) -> None:
            self.activity_label.setText(text)
            self.statusBar().showMessage(text)

        def _set_wait_cursor(self, busy: bool) -> None:
            app = QtWidgets.QApplication.instance()
            if app is None:
                return
            if busy:
                if self._busy_cursor_depth == 0:
                    app.setOverrideCursor(QtGui.QCursor(QtCore.Qt.WaitCursor))
                self._busy_cursor_depth += 1
                return
            if self._busy_cursor_depth == 0:
                return
            self._busy_cursor_depth -= 1
            if self._busy_cursor_depth == 0:
                app.restoreOverrideCursor()

        def _begin_indeterminate_progress(self) -> None:
            self._progress_done = 0
            self._progress_total = 0
            self.progress_bar.setRange(0, 0)

        def _advance_progress(self) -> None:
            self._progress_done += 1
            if self._progress_total < self._progress_done:
                self._progress_total = self._progress_done
                self.progress_bar.setRange(0, self._progress_total)
            self.progress_bar.setValue(self._progress_done)

        def _finish_progress(self) -> None:
            if self.progress_bar.maximum() == 0:
                self.progress_bar.setRange(0, 100)
                self.progress_bar.setValue(100)
                return
            self.progress_bar.setValue(self.progress_bar.maximum())

        def _reset_progress(self) -> None:
            self._progress_done = 0
            self._progress_total = 0
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

        def _set_summary(self, root: Node | None) -> None:
            if root is None:
                self.summary_label.setText("")
                return
            counts = _tree_counts(root)
            self.summary_label.setText(
                f"{counts['projects']} projects  /  "
                f"{counts['branches']} branches  /  "
                f"{counts['errors']} errors"
            )

        def _on_selection_changed(self, current, _previous) -> None:
            node = current.data(0, NODE_ROLE) if current is not None else None
            self.sync_selected_action.setEnabled(
                node is not None and not self._is_busy()
            )
            if node is None:
                self.detail_title.setText("No node selected")
                self.detail_meta.setText("")
                self.detail_path.setText("")
                self.log.clear()
                return
            self._show_node_details(node)

        def _refresh_selected_details(self) -> None:
            node = self.project_tree.selected_node()
            if node is not None:
                self._show_node_details(node)

        def _show_node_details(self, node: Node) -> None:
            status = _node_status_text(node)
            dirty = "dirty" if node.is_dirty() else "clean"
            local = "local" if node.state.presence.exists_locally else "remote only"
            scanned = "scanned" if node.is_scanned() else "not scanned"
            self.detail_title.setText(node.name)
            self.detail_meta.setText(
                f"{_node_kind(node)}  /  {status}  /  "
                f"{dirty}  /  {local}  /  {scanned}"
            )
            self.detail_path.setText(_safe_relative_path(node))
            lines = node.state.log.lines
            self.log.setPlainText("\n".join(lines) if lines else "No log entries.")


    class TrayController:
        def __init__(self, app, window: MainWindow):
            self._app = app
            self._window = window
            self._tray = QtWidgets.QSystemTrayIcon(_app_icon(), app)
            self._tray.setToolTip("Echogit")

            menu = QtWidgets.QMenu()
            show_action = menu.addAction("Open")
            show_action.triggered.connect(self._show_window)
            menu.addAction(window.refresh_action)
            menu.addAction(window.sync_action)
            menu.addAction(window.sync_selected_action)
            menu.addSeparator()
            menu.addAction(window.quit_action)
            self._tray.setContextMenu(menu)
            self._tray.activated.connect(self._on_activated)

        def show(self) -> None:
            self._tray.show()

        def _show_window(self) -> None:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()

        def _on_activated(self, reason) -> None:
            if reason == QtWidgets.QSystemTrayIcon.Trigger:
                self._show_window()


def _app_icon():
    icon = QtGui.QIcon.fromTheme("folder-sync")
    if not icon.isNull():
        return icon
    return QtWidgets.QApplication.style().standardIcon(
        QtWidgets.QStyle.SP_DriveNetIcon
    )


def _theme_icon(name: str, fallback: str):
    icon = QtGui.QIcon.fromTheme(name)
    if not icon.isNull():
        return icon
    style = QtWidgets.QApplication.style()
    fallbacks = {
        "Refresh": QtWidgets.QStyle.SP_BrowserReload,
        "Sync": QtWidgets.QStyle.SP_DialogApplyButton,
        "SyncSelected": QtWidgets.QStyle.SP_ArrowRight,
        "Quit": QtWidgets.QStyle.SP_DialogCloseButton,
        "Folder": QtWidgets.QStyle.SP_DirIcon,
        "Git": QtWidgets.QStyle.SP_DriveHDIcon,
        "Rsync": QtWidgets.QStyle.SP_DriveNetIcon,
        "Peer": QtWidgets.QStyle.SP_ComputerIcon,
        "Branch": QtWidgets.QStyle.SP_FileDialogDetailedView,
        "Ready": QtWidgets.QStyle.SP_DialogApplyButton,
        "Error": QtWidgets.QStyle.SP_MessageBoxCritical,
        "Dirty": QtWidgets.QStyle.SP_MessageBoxWarning,
        "Unknown": QtWidgets.QStyle.SP_MessageBoxQuestion,
        "Remote": QtWidgets.QStyle.SP_DriveNetIcon,
    }
    return style.standardIcon(fallbacks[fallback])


def _node_can_expand(node: Node) -> bool:
    return (
        bool(node.children)
        or node.is_folder
        or isinstance(node, (ProjectNode, PeerNode))
    )


def _node_icon(node: Node):
    if isinstance(node, BranchNode):
        return _theme_icon("vcs-branch", "Branch")
    if isinstance(node, PeerNode):
        return _theme_icon("computer", "Peer")
    if isinstance(node, GitProjectNode):
        return _theme_icon("git", "Git")
    if isinstance(node, RsyncProjectNode):
        return _theme_icon("folder-remote", "Rsync")
    if isinstance(node, FolderNode):
        return _theme_icon("folder", "Folder")
    return _theme_icon("text-x-generic", "Unknown")


def _node_status_icon(node: Node):
    status = _node_status_text(node)
    if status == "ERR":
        return _theme_icon("dialog-error", "Error")
    if status in {"STALE", "DIRTY"}:
        return _theme_icon("dialog-warning", "Dirty")
    if status == "REMOTE":
        return _theme_icon("network-server", "Remote")
    if status in {"UNK", "SYNC?"}:
        return _theme_icon("dialog-question", "Unknown")
    return _theme_icon("emblem-default", "Ready")


def _node_kind(node: Node) -> str:
    if isinstance(node, BranchNode):
        return "Branch"
    if isinstance(node, PeerNode):
        return "Peer"
    if isinstance(node, GitProjectNode):
        return "Git"
    if isinstance(node, RsyncProjectNode):
        return "Rsync"
    if node.is_folder:
        return "Folder"
    return "Node"


def _node_status_text(node: Node) -> str:
    if node.has_error() or node.sync_state() == "error":
        return "ERR"
    if not node.is_folder and not node.state.presence.exists_locally:
        return "REMOTE"
    if not node.is_scanned():
        return "UNK"
    if node.sync_state() == "ok":
        return "STALE" if node.is_dirty() else "SYNCED"
    if node.is_dirty():
        return "DIRTY"
    if node.sync_state() == "unknown":
        return "SYNC?"
    return "OK"


def _node_status_brush(node: Node):
    status = _node_status_text(node)
    colors = {
        "ERR": "#b91c1c",
        "REMOTE": "#2563a0",
        "UNK": "#a16207",
        "SYNC?": "#a16207",
        "STALE": "#a16207",
        "DIRTY": "#a16207",
        "SYNCED": "#047857",
        "OK": "#047857",
    }
    return QtGui.QBrush(QtGui.QColor(colors.get(status, "#59645f")))


def _safe_relative_path(node: Node) -> str:
    try:
        return str(node.relative_path)
    except ValueError:
        return str(node.path)


def _tree_counts(node: Node) -> dict[str, int]:
    counts = {
        "projects": 1 if isinstance(node, ProjectNode) else 0,
        "branches": 1 if isinstance(node, BranchNode) else 0,
        "errors": 1 if _node_has_own_error(node) else 0,
    }
    for child in list(node.children):
        child_counts = _tree_counts(child)
        counts["projects"] += child_counts["projects"]
        counts["branches"] += child_counts["branches"]
        counts["errors"] += child_counts["errors"]
    return counts


def _node_has_own_error(node: Node) -> bool:
    return node.state.log.has_error or node.sync_state() == "error"


def _sync_progress_total(node: Node) -> int:
    total = 1
    for child in list(node.children):
        total += _sync_progress_total(child)
    return total


def _style_sheet() -> str:
    return """
    QMainWindow {
        background: #f4f6f7;
        color: #1f2528;
    }
    QToolBar {
        background: #ffffff;
        border: 0;
        border-bottom: 1px solid #d9dee2;
        spacing: 6px;
        padding: 7px 10px;
    }
    QToolButton {
        background: #f8fafb;
        border: 1px solid #cdd5da;
        border-radius: 4px;
        color: #20272b;
        padding: 6px 11px;
    }
    QToolButton:hover {
        background: #eaf2ee;
        border-color: #6aa084;
    }
    QFrame#headerBand {
        background: #283237;
        border: 0;
        border-bottom: 1px solid #1c2428;
    }
    QLabel#windowTitle {
        color: #ffffff;
        font-size: 20px;
        font-weight: 700;
    }
    QLabel#summaryLabel {
        color: #c8d6d2;
        font-size: 13px;
    }
    QLabel#activityLabel {
        background: #d7ede4;
        border-radius: 4px;
        color: #164436;
        font-weight: 600;
        padding: 4px 9px;
    }
    QProgressBar#progressBar {
        background: #1e292d;
        border: 1px solid #425257;
        border-radius: 4px;
    }
    QProgressBar#progressBar::chunk {
        background: #7fc29c;
        border-radius: 3px;
    }
    QHeaderView::section {
        background: #edf1f3;
        border: 0;
        border-bottom: 1px solid #d4dce0;
        color: #2d383d;
        font-weight: 600;
        padding: 8px 9px;
    }
    QTreeWidget {
        background: #ffffff;
        alternate-background-color: #f7f9fa;
        border: 0;
        selection-background-color: #d8eadf;
        selection-color: #17211c;
        outline: 0;
    }
    QTreeWidget::item {
        min-height: 28px;
        padding: 4px 8px;
        border: 0;
    }
    QTreeWidget::branch {
        background: transparent;
    }
    QFrame#detailsPanel {
        background: #ffffff;
        border: 0;
        border-left: 1px solid #d9dee2;
        border-bottom: 1px solid #d9dee2;
    }
    QLabel#detailTitle {
        color: #1f2528;
        font-size: 16px;
        font-weight: 700;
    }
    QLabel#detailMeta {
        color: #637076;
        font-size: 12px;
        font-weight: 600;
    }
    QLabel#detailPath {
        color: #47545a;
        font-size: 12px;
    }
    QPlainTextEdit {
        background: #20272b;
        color: #eef4f1;
        border: 0;
        border-left: 1px solid #151b1e;
        padding: 12px;
        font-family: monospace;
    }
    QStatusBar {
        background: #ffffff;
        border-top: 1px solid #d9dee2;
        color: #526167;
    }
    """


if __name__ == "__main__":
    raise SystemExit(main())
