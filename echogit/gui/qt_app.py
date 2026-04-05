from __future__ import annotations

import sys

from echogit.config import Config
from echogit.core import EchogitService, ProjectItem, SyncProgress

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

    REL_ROLE = QtCore.Qt.UserRole + 1

    class SyncWorker(QtCore.QObject):
        progress = QtCore.Signal(object)
        finished = QtCore.Signal(object)
        failed = QtCore.Signal(str)

        def __init__(self, service: EchogitService):
            super().__init__()
            self._service = service

        @QtCore.Slot()
        def run(self) -> None:
            try:
                result = self._service.sync(on_progress=self._on_progress)
            except Exception as exc:  # pylint: disable=broad-exception-caught
                self.failed.emit(str(exc))
                return
            self.finished.emit(result)

        def _on_progress(self, progress: SyncProgress) -> None:
            self.progress.emit(progress)


    class ProjectTree(QtWidgets.QTreeWidget):
        HEADERS = ["Project", "Type", "State"]

        def __init__(self):
            super().__init__()
            self.setColumnCount(len(self.HEADERS))
            self.setHeaderLabels(self.HEADERS)
            self.setRootIsDecorated(True)
            self.setAlternatingRowColors(True)
            self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.setUniformRowHeights(True)
            self.setIndentation(18)
            self.setAnimated(True)
            self._project_items: dict[str, QtWidgets.QTreeWidgetItem] = {}

            header = self.header()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

        def set_projects(self, projects: list[ProjectItem]) -> None:
            self.clear()
            self._project_items.clear()
            folders: dict[tuple[str, ...], QtWidgets.QTreeWidgetItem] = {}
            for project in sorted(projects, key=lambda item: str(item.rel)):
                self._append_project(project, folders)
            self.expandToDepth(1)

        def mark_progress(self, progress: SyncProgress) -> None:
            item = self._project_items.get(str(progress.rel))
            if item is None:
                return
            item.setText(2, _status_label(progress))
            item.setIcon(2, _status_icon(progress))
            item.setForeground(2, _status_brush(progress))

        def selected_project_rel(self) -> str | None:
            item = self.currentItem()
            if item is None:
                return None
            return item.data(0, REL_ROLE)

        def _append_project(
            self,
            project: ProjectItem,
            folders: dict[tuple[str, ...], QtWidgets.QTreeWidgetItem],
        ) -> None:
            parts = project.rel.parts
            parent_item: QtWidgets.QTreeWidgetItem | None = None
            for idx, part in enumerate(parts[:-1]):
                key = parts[: idx + 1]
                folder_item = folders.get(key)
                if folder_item is None:
                    folder_item = QtWidgets.QTreeWidgetItem([part, "", ""])
                    folder_item.setIcon(0, _folder_icon())
                    folder_item.setForeground(0, QtGui.QBrush(QtGui.QColor("#39423d")))
                    folder_item.setData(0, REL_ROLE, None)
                    if parent_item is None:
                        self.addTopLevelItem(folder_item)
                    else:
                        parent_item.addChild(folder_item)
                    folders[key] = folder_item
                parent_item = folder_item

            name = parts[-1] if parts else str(project.rel)
            item = QtWidgets.QTreeWidgetItem([name, project.type, "Ready"])
            item.setData(0, REL_ROLE, str(project.rel))
            item.setToolTip(0, str(project.rel))
            item.setIcon(0, _project_icon(project.type))
            item.setIcon(2, _ready_icon())
            item.setForeground(2, QtGui.QBrush(QtGui.QColor("#59645f")))
            if parent_item is None:
                self.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            self._project_items[str(project.rel)] = item


    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, service: EchogitService):
            super().__init__()
            self._service = service
            self._thread: QtCore.QThread | None = None
            self._worker: SyncWorker | None = None
            self.setWindowTitle("Echogit")
            self.resize(1080, 680)

            self.project_tree = ProjectTree()
            self.project_tree.currentItemChanged.connect(self._on_selection_changed)

            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("No sync activity yet.")

            self.summary_label = QtWidgets.QLabel("")
            self.summary_label.setObjectName("summaryLabel")
            self.activity_label = QtWidgets.QLabel("Ready")
            self.activity_label.setObjectName("activityLabel")
            self.detail_title = QtWidgets.QLabel("No project selected")
            self.detail_title.setObjectName("detailTitle")
            self.detail_meta = QtWidgets.QLabel("")
            self.detail_meta.setObjectName("detailMeta")

            details = QtWidgets.QFrame()
            details.setObjectName("detailsPanel")
            details_layout = QtWidgets.QVBoxLayout(details)
            details_layout.setContentsMargins(16, 14, 16, 14)
            details_layout.setSpacing(8)
            details_layout.addWidget(self.detail_title)
            details_layout.addWidget(self.detail_meta)
            details_layout.addStretch(1)

            right_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            right_splitter.addWidget(details)
            right_splitter.addWidget(self.log)
            right_splitter.setSizes([170, 360])

            splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal)
            splitter.addWidget(self.project_tree)
            splitter.addWidget(right_splitter)
            splitter.setSizes([640, 390])

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

            central = QtWidgets.QWidget()
            central_layout = QtWidgets.QVBoxLayout(central)
            central_layout.setContentsMargins(0, 0, 0, 0)
            central_layout.setSpacing(0)
            central_layout.addWidget(header)
            central_layout.addWidget(splitter, 1)
            self.setCentralWidget(central)

            self.refresh_action = QtGui.QAction("Refresh", self)
            self.refresh_action.setIcon(_theme_icon("view-refresh", "Refresh"))
            self.refresh_action.setToolTip("Refresh projects")
            self.refresh_action.triggered.connect(self.refresh_projects)
            self.sync_action = QtGui.QAction("Sync All", self)
            self.sync_action.setIcon(_theme_icon("emblem-synchronizing", "Sync"))
            self.sync_action.setToolTip("Sync all projects")
            self.sync_action.triggered.connect(self.sync_all)
            self.quit_action = QtGui.QAction("Quit", self)
            self.quit_action.setIcon(_theme_icon("application-exit", "Quit"))
            self.quit_action.triggered.connect(QtWidgets.QApplication.quit)

            toolbar = QtWidgets.QToolBar("Main")
            toolbar.setMovable(False)
            toolbar.setIconSize(QtCore.QSize(20, 20))
            toolbar.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
            toolbar.addAction(self.refresh_action)
            toolbar.addAction(self.sync_action)
            self.addToolBar(toolbar)

            self.statusBar().showMessage("Ready")
            self.refresh_projects()

        def refresh_projects(self) -> None:
            self._set_activity("Scanning projects...")
            projects = self._service.list_projects()
            self.project_tree.set_projects(projects)
            self._set_summary(projects)
            self._write_log(f"Found {len(projects)} local project(s).")
            self._set_activity("Ready")

        def sync_all(self) -> None:
            if self._thread is not None:
                return
            self.sync_action.setEnabled(False)
            self.refresh_action.setEnabled(False)
            self._set_activity("Syncing...")
            self._write_log("Sync started.")

            self._thread = QtCore.QThread(self)
            self._worker = SyncWorker(self._service)
            self._worker.moveToThread(self._thread)
            self._thread.started.connect(self._worker.run)
            self._worker.progress.connect(self._on_sync_progress)
            self._worker.finished.connect(self._on_sync_finished)
            self._worker.failed.connect(self._on_sync_failed)
            self._worker.finished.connect(self._thread.quit)
            self._worker.failed.connect(self._thread.quit)
            self._thread.finished.connect(self._cleanup_worker)
            self._thread.start()

        def _on_sync_progress(self, progress: SyncProgress) -> None:
            self.project_tree.mark_progress(progress)
            state = _status_label(progress)
            self._write_log(f"{state}: {progress.rel}")

        def _on_sync_finished(self, result) -> None:
            if result.ok:
                self._set_activity("Sync OK")
                self._write_log("Sync OK.")
            else:
                self._set_activity("Sync failed")
                self._write_log("Sync failed.")

        def _on_sync_failed(self, message: str) -> None:
            self._set_activity("Sync failed")
            self._write_log(f"ERROR: {message}")

        def _cleanup_worker(self) -> None:
            self.sync_action.setEnabled(True)
            self.refresh_action.setEnabled(True)
            self._worker = None
            self._thread = None
            self.refresh_projects()

        def _write_log(self, message: str) -> None:
            self.log.appendPlainText(message)

        def _set_activity(self, text: str) -> None:
            self.activity_label.setText(text)
            self.statusBar().showMessage(text)

        def _set_summary(self, projects: list[ProjectItem]) -> None:
            git_count = sum(1 for project in projects if project.type == "git")
            rsync_count = sum(1 for project in projects if project.type == "rsync")
            self.summary_label.setText(
                f"{len(projects)} projects  /  {git_count} git  /  {rsync_count} rsync"
            )

        def _on_selection_changed(self, current, _previous) -> None:
            if current is None:
                self.detail_title.setText("No project selected")
                self.detail_meta.setText("")
                return
            rel = current.data(0, REL_ROLE)
            if rel is None:
                self.detail_title.setText(current.text(0))
                self.detail_meta.setText("Folder")
                return
            self.detail_title.setText(rel)
            self.detail_meta.setText(f"{current.text(1).upper()}  /  {current.text(2)}")


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
        "Quit": QtWidgets.QStyle.SP_DialogCloseButton,
        "Folder": QtWidgets.QStyle.SP_DirIcon,
        "Git": QtWidgets.QStyle.SP_DriveHDIcon,
        "Rsync": QtWidgets.QStyle.SP_DriveNetIcon,
        "Ready": QtWidgets.QStyle.SP_DialogApplyButton,
        "Error": QtWidgets.QStyle.SP_MessageBoxCritical,
        "Dirty": QtWidgets.QStyle.SP_MessageBoxWarning,
    }
    return style.standardIcon(fallbacks[fallback])


def _folder_icon():
    return _theme_icon("folder", "Folder")


def _project_icon(project_type: str):
    if project_type == "rsync":
        return _theme_icon("folder-remote", "Rsync")
    return _theme_icon("git", "Git")


def _ready_icon():
    return _theme_icon("emblem-default", "Ready")


def _status_icon(progress: SyncProgress):
    if not progress.ok:
        return _theme_icon("dialog-error", "Error")
    if progress.dirty:
        return _theme_icon("dialog-warning", "Dirty")
    return _ready_icon()


def _status_label(progress: SyncProgress) -> str:
    if not progress.ok:
        return "Error"
    if progress.dirty:
        return "Dirty"
    return "Synced"


def _status_brush(progress: SyncProgress):
    if not progress.ok:
        return QtGui.QBrush(QtGui.QColor("#b91c1c"))
    if progress.dirty:
        return QtGui.QBrush(QtGui.QColor("#a16207"))
    return QtGui.QBrush(QtGui.QColor("#047857"))


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
