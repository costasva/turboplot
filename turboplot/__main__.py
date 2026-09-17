from __future__ import annotations

import sys

from .compat import unhide_qt_plugins

unhide_qt_plugins()

from PyQt6.QtWidgets import QApplication

from . import datagen, db, theme as theme_mod
from .mainwindow import MainWindow
from .state import SessionState


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    rebuild = "--rebuild" in argv
    if rebuild:
        argv.remove("--rebuild")
    path = datagen.build(force=rebuild)

    app = QApplication(argv)
    app.setApplicationName("TurboPlot")
    theme = theme_mod.Theme(dark=False)
    conn = db.connect(path)
    state = SessionState(conn, theme)
    window = MainWindow(state)
    window.setStyleSheet(theme_mod.qt_stylesheet(theme))
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
