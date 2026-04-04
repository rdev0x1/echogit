from __future__ import annotations

import sys
from pathlib import Path

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


    class ProjectTable(QtWidgets.QTableWidget):
        HEADERS = ["Project", "Type", "State"]

        def __init__(self):
            super().__init__(0, len(self.HEADERS))
            self.setHorizontalHeaderLabels(self.HEADERS)
            self.verticalHeader().setVisible(False)
            self.setAlternatingRowColors(True)
            self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
            self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
            self.setShowGrid(False)
            header = self.horizontalHeader()
            header.setStretchLastSection(False)
            header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
            header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
            header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)

        def set_projects(self, projects: list[ProjectItem]) -> None:
            self.setRowCount(0)
            for project in projects:
                self._append_project(project)

        def mark_progress(self, progress: SyncProgress) -> None:
            rel = str(progress.rel)
            for row in range(self.rowCount()):
                if self.item(row, 0).text() == rel:
                    self.item(row, 2).setText(_status_label(progress))
                    self.item(row, 2).setForeground(_status_brush(progress))
                    return

        def _append_project(self, project: ProjectItem) -> None:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, 0, QtWidgets.QTableWidgetItem(str(project.rel)))
            self.setItem(row, 1, QtWidgets.QTableWidgetItem(project.type))
            self.setItem(row, 2, QtWidgets.QTableWidgetItem("Ready"))


    class MainWindow(QtWidgets.QMainWindow):
        def __init__(self, service: EchogitService):
            super().__init__()
            self._service = service
            self._thread: QtCore.QThread | None = None
            self._worker: SyncWorker | None = None
            self.setWindowTitle("Echogit")
            self.resize(920, 620)

            self.project_table = ProjectTable()
            self.log = QtWidgets.QPlainTextEdit()
            self.log.setReadOnly(True)
            self.log.setPlaceholderText("Sync activity appears here.")

            splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical)
            splitter.addWidget(self.project_table)
            splitter.addWidget(self.log)
            splitter.setSizes([420, 160])
            self.setCentralWidget(splitter)

            self.refresh_action = QtGui.QAction("Refresh", self)
            self.refresh_action.triggered.connect(self.refresh_projects)
            self.sync_action = QtGui.QAction("Sync All", self)
            self.sync_action.triggered.connect(self.sync_all)
            self.quit_action = QtGui.QAction("Quit", self)
            self.quit_action.triggered.connect(QtWidgets.QApplication.quit)

            toolbar = QtWidgets.QToolBar("Main")
            toolbar.setMovable(False)
            toolbar.addAction(self.refresh_action)
            toolbar.addAction(self.sync_action)
            self.addToolBar(toolbar)

            self.statusBar().showMessage("Ready")
            self.refresh_projects()

        def refresh_projects(self) -> None:
            self.statusBar().showMessage("Scanning projects...")
            projects = self._service.list_projects()
            self.project_table.set_projects(projects)
            self._write_log(f"Found {len(projects)} local project(s).")
            self.statusBar().showMessage("Ready")

        def sync_all(self) -> None:
            if self._thread is not None:
                return
            self.sync_action.setEnabled(False)
            self.refresh_action.setEnabled(False)
            self.statusBar().showMessage("Syncing...")
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
            self.project_table.mark_progress(progress)
            state = _status_label(progress)
            self._write_log(f"{state}: {progress.rel}")

        def _on_sync_finished(self, result) -> None:
            if result.ok:
                self.statusBar().showMessage("Sync OK")
                self._write_log("Sync OK.")
            else:
                self.statusBar().showMessage("Sync failed")
                self._write_log("Sync failed.")

        def _on_sync_failed(self, message: str) -> None:
            self.statusBar().showMessage("Sync failed")
            self._write_log(f"ERROR: {message}")

        def _cleanup_worker(self) -> None:
            self.sync_action.setEnabled(True)
            self.refresh_action.setEnabled(True)
            self._worker = None
            self._thread = None
            self.refresh_projects()

        def _write_log(self, message: str) -> None:
            self.log.appendPlainText(message)


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
        background: #f7f7f4;
        color: #232522;
    }
    QToolBar {
        background: #ecece7;
        border: 0;
        border-bottom: 1px solid #d7d8d1;
        spacing: 6px;
        padding: 6px;
    }
    QToolButton {
        background: #ffffff;
        border: 1px solid #cfd2c8;
        border-radius: 4px;
        padding: 6px 12px;
    }
    QToolButton:hover {
        background: #f3f6ee;
        border-color: #9aa68a;
    }
    QHeaderView::section {
        background: #dfe4d6;
        border: 0;
        border-bottom: 1px solid #c3c9bb;
        color: #2c3328;
        font-weight: 600;
        padding: 7px 8px;
    }
    QTableWidget {
        background: #ffffff;
        alternate-background-color: #f4f6f0;
        border: 0;
        selection-background-color: #d3e4c5;
        selection-color: #1f271c;
    }
    QTableWidget::item {
        padding: 6px 8px;
        border: 0;
    }
    QPlainTextEdit {
        background: #242823;
        color: #ecf2e8;
        border: 0;
        padding: 10px;
        font-family: monospace;
    }
    QStatusBar {
        background: #ecece7;
        border-top: 1px solid #d7d8d1;
    }
    """


if __name__ == "__main__":
    raise SystemExit(main())
