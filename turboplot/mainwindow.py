"""Main window: plot tree + loaded-data lists on the left, plot tabs in the
middle, per-plot series control on the right."""
from __future__ import annotations

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QKeySequence, QPainter, QPixmap
from PyQt6.QtWidgets import (QAbstractItemView, QCheckBox, QDialog, QDialogButtonBox,
                             QDockWidget, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
                             QSplitter, QTabWidget, QToolBar, QTreeWidget,
                             QTreeWidgetItem, QVBoxLayout, QWidget)

from . import db, theme as theme_mod
from .plotpanel import PlotPanel
from .state import SessionState

DEFAULT_TABS = [
    ("machine", "eff_vs_flow"),
    ("machine", "poly_eff"),
    ("r1", "max_strain"),
    ("r1", "exit_pt_ratio"),
]


def swatch(color: str, size: int = 12, ring: str | None = None) -> QIcon:
    pm = QPixmap(size + 4, size + 4)
    pm.fill(QColor(0, 0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(QColor(ring) if ring else QColor(color))
    p.drawEllipse(2, 2, size, size)
    p.end()
    return QIcon(pm)


class LoadDialog(QDialog):
    """Stands in for 'pull results from the analysis archive'."""

    def __init__(self, parent, sources: list[db.Source], title: str, blurb: str):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        note = QLabel(blurb)
        note.setObjectName("sectionNote")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for s in sources:
            detail = s.notes if s.is_design else f"{s.ref_type} — {s.notes}"
            item = QListWidgetItem(f"{s.label}   —   {detail}")
            item.setData(Qt.ItemDataRole.UserRole, s.source_id)
            self.list.addItem(item)
        if sources:
            self.list.setCurrentRow(0)
        layout.addWidget(self.list)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.list.itemDoubleClicked.connect(lambda _i: self.accept())

    def chosen(self) -> list[str]:
        return [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems()]


class MainWindow(QMainWindow):
    def __init__(self, state: SessionState):
        super().__init__()
        self.state = state
        self.setWindowTitle("TurboPlot — CMP-8 design iteration results  [mockup]")
        self.resize(1560, 950)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.tabCloseRequested.connect(lambda i: self.tabs.removeTab(i))
        self.tabs.currentChanged.connect(lambda _i: self._refresh_series_dock())
        self.setCentralWidget(self.tabs)

        self._build_left_dock()
        self._build_right_dock()
        self._build_toolbar()
        self.statusBar().showMessage("Ready")

        state.sourcesChanged.connect(self._on_sources_changed)
        state.visibilityChanged.connect(self._on_visibility_changed)
        state.plotSeriesChanged.connect(lambda _k: self._refresh_all_panels())

        self._populate_tree()
        self._refresh_source_lists()
        for comp, metric in DEFAULT_TABS:
            spec = self._spec(comp, metric)
            if spec:
                self.open_plot(spec)
        self.tabs.setCurrentIndex(0)

    # -- construction -----------------------------------------------------
    def _spec(self, comp_key: str, metric_key: str) -> db.PlotSpec | None:
        for s in self.state.catalog:
            if s.comp_key == comp_key and s.metric_key == metric_key:
                return s
        return None

    def _build_left_dock(self) -> None:
        dock = QDockWidget("Available plots  •  Loaded data", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # --- plot tree ---
        tree_box = QWidget()
        tv = QVBoxLayout(tree_box)
        tv.setContentsMargins(0, 0, 0, 0)
        tv.setSpacing(4)
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Filter plots…")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.textChanged.connect(self._apply_filter)
        tv.addWidget(self.filter_edit)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.itemActivated.connect(self._on_tree_activated)
        self.tree.itemClicked.connect(self._on_tree_clicked)
        tv.addWidget(self.tree, 1)
        hint = QLabel("Double-click a plot to open it in a tab")
        hint.setObjectName("sectionNote")
        tv.addWidget(hint)
        splitter.addWidget(tree_box)

        # --- design iterations ---
        design_box = QWidget()
        dv = QVBoxLayout(design_box)
        dv.setContentsMargins(0, 0, 0, 0)
        dv.setSpacing(4)
        head = QLabel("Design iterations")
        head.setStyleSheet("font-weight: 600;")
        dv.addWidget(head)
        self.design_list = QListWidget()
        self.design_list.itemChanged.connect(self._on_design_item_changed)
        self.design_list.currentItemChanged.connect(self._on_source_selected)
        dv.addWidget(self.design_list, 1)
        row = QHBoxLayout()
        row.setSpacing(4)
        for text, slot, tip in [
            ("Load…", self.load_designs, "Pull another design iteration from the results archive"),
            ("All", lambda: self._set_all_designs(True), "Show every loaded design on every plot"),
            ("None", lambda: self._set_all_designs(False), "Hide every design"),
            ("Remove", self.remove_design, "Unload the selected design iteration"),
        ]:
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b)
        dv.addLayout(row)
        splitter.addWidget(design_box)

        # --- reference data ---
        ref_box = QWidget()
        rv = QVBoxLayout(ref_box)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(4)
        head = QLabel("Reference data")
        head.setStyleSheet("font-weight: 600;")
        rv.addWidget(head)
        self.ref_list = QListWidget()
        self.ref_list.itemChanged.connect(self._on_ref_item_changed)
        self.ref_list.currentItemChanged.connect(self._on_source_selected)
        rv.addWidget(self.ref_list, 1)
        b = QPushButton("Load reference dataset…")
        b.clicked.connect(self.load_references)
        rv.addWidget(b)
        splitter.addWidget(ref_box)

        splitter.setSizes([440, 260, 170])
        outer.addWidget(splitter, 1)

        self.details = QLabel("Select a design iteration or reference dataset to see its details.")
        self.details.setObjectName("sectionNote")
        self.details.setWordWrap(True)
        self.details.setMinimumHeight(64)
        self.details.setAlignment(Qt.AlignmentFlag.AlignTop)
        outer.addWidget(self.details)

        dock.setWidget(container)
        dock.setMinimumWidth(330)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)

    def _build_right_dock(self) -> None:
        dock = QDockWidget("Series on this plot", self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(6, 6, 6, 6)
        v.setSpacing(5)
        note = QLabel("Hide a series here to take it off this plot only. "
                      "The left-hand list controls every plot at once.")
        note.setObjectName("sectionNote")
        note.setWordWrap(True)
        v.addWidget(note)
        self.series_list = QListWidget()
        self.series_list.itemChanged.connect(self._on_series_item_changed)
        v.addWidget(self.series_list, 1)
        row = QHBoxLayout()
        for text, slot in [("All", lambda: self._set_all_series(True)),
                           ("None", lambda: self._set_all_series(False)),
                           ("Follow global", self._reset_series)]:
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        v.addLayout(row)
        dock.setWidget(box)
        dock.setMinimumWidth(240)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setIconSize(QSize(16, 16))
        tb.setMovable(False)
        self.addToolBar(tb)

        act = QAction("Load design iteration…", self)
        act.setShortcut(QKeySequence("Ctrl+L"))
        act.triggered.connect(self.load_designs)
        tb.addAction(act)

        act = QAction("Load reference data…", self)
        act.triggered.connect(self.load_references)
        tb.addAction(act)
        tb.addSeparator()

        act = QAction("Export plot…", self)
        act.setShortcut(QKeySequence("Ctrl+E"))
        act.setToolTip("Save this plot as PNG, PDF, SVG or an Excel workbook")
        act.triggered.connect(self._export_current)
        tb.addAction(act)

        act = QAction("Export to Excel…", self)
        act.setShortcut(QKeySequence("Ctrl+Shift+E"))
        act.setToolTip("Write the data behind this plot, and the plot itself as a "
                       "native Excel chart, to a workbook")
        act.triggered.connect(self._export_excel)
        tb.addAction(act)

        act = QAction("Close all tabs", self)
        act.triggered.connect(self.tabs.clear)
        tb.addAction(act)
        tb.addSeparator()

        self.dark_check = QCheckBox("Dark theme")
        self.dark_check.toggled.connect(self._toggle_dark)
        tb.addWidget(self.dark_check)

        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy().Expanding,
                             spacer.sizePolicy().verticalPolicy().Preferred)
        tb.addWidget(spacer)
        self.count_label = QLabel()
        self.count_label.setObjectName("hint")
        tb.addWidget(self.count_label)

    # -- tree -------------------------------------------------------------
    def _populate_tree(self) -> None:
        self.tree.clear()
        parents: dict[str, QTreeWidgetItem] = {}
        kind_icon = {"scalar": "▪", "curve": "⌒", "profile": "↕"}
        for spec in self.state.catalog:
            parent = parents.get(spec.comp_key)
            if parent is None:
                parent = QTreeWidgetItem(self.tree, [spec.comp_name])
                font = parent.font(0)
                font.setBold(True)
                parent.setFont(0, font)
                parent.setExpanded(spec.comp_key in ("machine", "r1"))
                parents[spec.comp_key] = parent
            leaf = QTreeWidgetItem(parent, [f"{kind_icon[spec.kind]}  {spec.title}"])
            leaf.setData(0, Qt.ItemDataRole.UserRole, spec.key)
            leaf.setToolTip(0, {
                "scalar": "One value per design iteration, plotted against design ID",
                "curve": "Swept over operating condition — one curve per design iteration",
                "profile": "Radial distribution — selected designs and operating points",
            }[spec.kind])

    def _apply_filter(self, text: str) -> None:
        text = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            shown = 0
            for j in range(parent.childCount()):
                child = parent.child(j)
                match = not text or text in child.text(0).lower() \
                    or text in parent.text(0).lower()
                child.setHidden(not match)
                shown += int(match)
            parent.setHidden(shown == 0)
            if text:
                parent.setExpanded(shown > 0)

    def _on_tree_activated(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key:
            self.open_plot(self._spec_by_key(key))
        else:
            item.setExpanded(not item.isExpanded())

    def _on_tree_clicked(self, item: QTreeWidgetItem, _col: int) -> None:
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if key and self._find_tab(key) is not None:
            self.open_plot(self._spec_by_key(key))     # focus an already-open plot

    def _spec_by_key(self, key: str) -> db.PlotSpec:
        return next(s for s in self.state.catalog if s.key == key)

    # -- tabs -------------------------------------------------------------
    def _find_tab(self, key: str) -> int | None:
        for i in range(self.tabs.count()):
            if self.tabs.widget(i).spec.key == key:
                return i
        return None

    def open_plot(self, spec: db.PlotSpec) -> None:
        existing = self._find_tab(spec.key)
        if existing is not None:
            self.tabs.setCurrentIndex(existing)
            return
        panel = PlotPanel(self.state, spec)
        index = self.tabs.addTab(panel, f"{spec.comp_name}: {spec.title}")
        self.tabs.setTabToolTip(index, spec.full_title)
        self.tabs.setCurrentIndex(index)
        self._refresh_series_dock()

    def _panels(self) -> list[PlotPanel]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def _refresh_all_panels(self) -> None:
        for panel in self._panels():
            panel.refresh()

    def _export_current(self) -> None:
        self._export(lambda panel: panel.export(), "Export plot")

    def _export_excel(self) -> None:
        self._export(lambda panel: panel.export_excel(), "Export to Excel")

    def _export(self, run, title: str) -> None:
        panel = self.tabs.currentWidget()
        if panel is None:
            QMessageBox.information(self, title, "Open a plot first.")
            return
        if panel.plot_data().is_empty:
            QMessageBox.information(self, title,
                                    "This plot has no series on it \u2014 nothing to export.")
            return
        path = run(panel)
        if path:
            self.statusBar().showMessage(f"Saved {path}", 8000)

    # -- source lists ------------------------------------------------------
    def _refresh_source_lists(self) -> None:
        for widget, sources, is_design in (
            (self.design_list, self.state.designs(loaded=True), True),
            (self.ref_list, self.state.references(loaded=True), False),
        ):
            widget.blockSignals(True)
            widget.clear()
            for src in sources:
                if is_design:
                    style = self.state.theme.design_style(src.color_slot or 0)
                    text = src.source_id
                    icon = swatch(style.color)
                else:
                    style = self.state.style_for(src)
                    text = f"{src.label}  –  {src.ref_type}"
                    icon = swatch(style.color, ring=self.state.theme.c["muted"])
                item = QListWidgetItem(icon, text)
                item.setData(Qt.ItemDataRole.UserRole, src.source_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked
                                   if self.state.is_visible(src.source_id)
                                   else Qt.CheckState.Unchecked)
                item.setToolTip(f"{src.label}\n{src.hardware} — {src.created}\n{src.notes}")
                widget.addItem(item)
            widget.blockSignals(False)
        n_des = len(self.state.designs(loaded=True))
        n_avail = len(self.state.designs(loaded=False))
        n_ref = len(self.state.references(loaded=True))
        self.count_label.setText(
            f"{n_des} design iterations loaded ({n_avail} more in the archive) "
            f"• {n_ref} reference datasets • {len(self.state.catalog)} plots available   ")

    def _on_design_item_changed(self, item: QListWidgetItem) -> None:
        self.state.set_global_visible(item.data(Qt.ItemDataRole.UserRole),
                                      item.checkState() == Qt.CheckState.Checked)

    _on_ref_item_changed = _on_design_item_changed

    def _on_source_selected(self, item: QListWidgetItem | None, _prev=None) -> None:
        if item is None:
            return
        src = self.state.source(item.data(Qt.ItemDataRole.UserRole))
        kind = "Design iteration" if src.is_design else f"Reference data — {src.ref_type}"
        self.details.setText(
            f"<b>{src.label}</b> — {kind}<br>{src.hardware} • {src.created}"
            f"<br><span>{src.notes}</span>")

    def _set_all_designs(self, visible: bool) -> None:
        for src in self.state.designs(loaded=True):
            self.state.set_global_visible(src.source_id, visible)
        self._refresh_source_lists()

    # -- loading / unloading ----------------------------------------------
    def load_designs(self) -> None:
        available = self.state.designs(loaded=False)
        if not available:
            QMessageBox.information(self, "Load design iteration",
                                    "Every design iteration in the archive is already loaded.")
            return
        dlg = LoadDialog(self, available, "Load design iteration",
                         "Design iterations found in the results archive. Loading one adds it "
                         "to every plot that is already open, and to any plot opened later.")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen():
            for sid in dlg.chosen():
                self.state.load_source(sid)
            self.statusBar().showMessage(
                f"Loaded {', '.join(dlg.chosen())} — added to "
                f"{self.tabs.count()} open plot(s)", 8000)

    def load_references(self) -> None:
        available = self.state.references(loaded=False)
        if not available:
            QMessageBox.information(self, "Load reference data",
                                    "Every reference dataset is already loaded.")
            return
        dlg = LoadDialog(self, available, "Load reference data",
                         "Rig tests, legacy analyses and benchmark machines available "
                         "for comparison.")
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.chosen():
            for sid in dlg.chosen():
                self.state.load_source(sid)
            self.statusBar().showMessage(f"Loaded reference data: {', '.join(dlg.chosen())}", 8000)

    def remove_design(self) -> None:
        item = self.design_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Remove design iteration",
                                    "Select a design iteration in the list first.")
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(
                self, "Remove design iteration",
                f"Unload {sid}? Its results stay in the database and can be loaded again."
        ) == QMessageBox.StandardButton.Yes:
            self.state.unload_source(sid)
            self.statusBar().showMessage(f"{sid} unloaded", 6000)

    def _on_sources_changed(self) -> None:
        self._refresh_source_lists()
        self._refresh_all_panels()
        self._refresh_series_dock()

    def _on_visibility_changed(self) -> None:
        self._refresh_all_panels()
        self._refresh_series_dock()

    # -- per-plot series dock ---------------------------------------------
    def _refresh_series_dock(self) -> None:
        panel = self.tabs.currentWidget()
        self.series_list.blockSignals(True)
        self.series_list.clear()
        if panel is not None:
            for src in self.state.candidates_for(panel.spec):
                style = self.state.style_for(src)
                icon = swatch(style.color, ring=None if src.is_design
                              else self.state.theme.c["muted"])
                label = src.source_id if src.is_design else src.label
                item = QListWidgetItem(icon, label)
                item.setData(Qt.ItemDataRole.UserRole, src.source_id)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                hidden_globally = src.source_id in self.state.hidden_globally
                item.setCheckState(
                    Qt.CheckState.Checked
                    if self.state.is_visible(src.source_id, panel.spec.key) and not hidden_globally
                    else Qt.CheckState.Unchecked)
                if hidden_globally:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
                    item.setToolTip("Hidden on every plot from the left-hand list")
                self.series_list.addItem(item)
        self.series_list.blockSignals(False)

    def _on_series_item_changed(self, item: QListWidgetItem) -> None:
        panel = self.tabs.currentWidget()
        if panel is None:
            return
        self.state.set_plot_visible(panel.spec.key, item.data(Qt.ItemDataRole.UserRole),
                                    item.checkState() == Qt.CheckState.Checked)

    def _set_all_series(self, visible: bool) -> None:
        panel = self.tabs.currentWidget()
        if panel is None:
            return
        for src in self.state.candidates_for(panel.spec):
            self.state.set_plot_visible(panel.spec.key, src.source_id, visible)
        self._refresh_series_dock()

    def _reset_series(self) -> None:
        panel = self.tabs.currentWidget()
        if panel is None:
            return
        self.state.reset_plot_overrides(panel.spec.key)
        self._refresh_series_dock()

    # -- theme -------------------------------------------------------------
    def _toggle_dark(self, dark: bool) -> None:
        self.state.theme.set_dark(dark)
        self.setStyleSheet(theme_mod.qt_stylesheet(self.state.theme))
        self._refresh_source_lists()
        self._refresh_series_dock()
        self._refresh_all_panels()
