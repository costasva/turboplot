"""Session state shared by every widget.

Holds what is loaded, what is visible globally, and the per-plot overrides.
Widgets never talk to each other directly -- they mutate this and listen to
its signals, so "load a new design iteration" reaches every open plot.
"""
from __future__ import annotations

import sqlite3

from PyQt6.QtCore import QObject, pyqtSignal

from . import db
from .theme import SeriesStyle, Theme


class SessionState(QObject):
    sourcesChanged = pyqtSignal()            # something was loaded / unloaded
    visibilityChanged = pyqtSignal()         # global show/hide changed
    plotSeriesChanged = pyqtSignal(str)      # per-plot override changed
    themeChanged = pyqtSignal()

    def __init__(self, conn: sqlite3.Connection, theme: Theme):
        super().__init__()
        self.conn = conn
        self.theme = theme
        self.catalog = db.plot_catalog(conn)
        self.hidden_globally: set[str] = set()
        self.hidden_in_plot: dict[str, set[str]] = {}
        self.show_references = True

    # -- queries -----------------------------------------------------------
    def designs(self, loaded: bool | None = None) -> list[db.Source]:
        return db.sources(self.conn, "design", loaded)

    def references(self, loaded: bool | None = None) -> list[db.Source]:
        return db.sources(self.conn, "reference", loaded)

    def source(self, source_id: str) -> db.Source:
        rows = [s for s in self.designs() + self.references() if s.source_id == source_id]
        return rows[0]

    def is_visible(self, source_id: str, plot_key: str | None = None) -> bool:
        if source_id in self.hidden_globally:
            return False
        if plot_key and source_id in self.hidden_in_plot.get(plot_key, set()):
            return False
        return True

    def style_for(self, source: db.Source) -> SeriesStyle:
        if source.is_design:
            return self.theme.design_style(source.color_slot or 0)
        order = [r.source_id for r in self.references()]
        return self.theme.reference_style(order.index(source.source_id))

    def series_for(self, spec: db.PlotSpec,
                   include_refs: bool = True) -> tuple[list[db.Source], list[db.Source]]:
        """(designs, references) that are loaded, have data for this plot and
        are not hidden globally or in this plot."""
        have = db.sources_with_data(self.conn, spec)
        designs = [s for s in self.designs(loaded=True)
                   if s.source_id in have and self.is_visible(s.source_id, spec.key)]
        refs = []
        if include_refs:
            refs = [s for s in self.references(loaded=True)
                    if s.source_id in have and self.is_visible(s.source_id, spec.key)]
        return designs, refs

    def candidates_for(self, spec: db.PlotSpec) -> list[db.Source]:
        """Everything loaded that could appear on this plot, hidden or not."""
        have = db.sources_with_data(self.conn, spec)
        return [s for s in self.designs(loaded=True) + self.references(loaded=True)
                if s.source_id in have]

    # -- mutations ---------------------------------------------------------
    def _next_color_slot(self) -> int:
        used = [s.color_slot for s in self.designs(loaded=True) if s.color_slot is not None]
        return (max(used) + 1) if used else 0

    def load_source(self, source_id: str) -> None:
        src = self.source(source_id)
        slot = self._next_color_slot() if src.is_design else None
        db.set_loaded(self.conn, source_id, True, slot)
        self.hidden_globally.discard(source_id)
        self.sourcesChanged.emit()

    def unload_source(self, source_id: str) -> None:
        db.set_loaded(self.conn, source_id, False)
        for hidden in self.hidden_in_plot.values():
            hidden.discard(source_id)
        self.sourcesChanged.emit()

    def set_global_visible(self, source_id: str, visible: bool) -> None:
        if visible:
            self.hidden_globally.discard(source_id)
        else:
            self.hidden_globally.add(source_id)
        self.visibilityChanged.emit()

    def set_plot_visible(self, plot_key: str, source_id: str, visible: bool) -> None:
        hidden = self.hidden_in_plot.setdefault(plot_key, set())
        if visible:
            hidden.discard(source_id)
        else:
            hidden.add(source_id)
        self.plotSeriesChanged.emit(plot_key)

    def reset_plot_overrides(self, plot_key: str) -> None:
        self.hidden_in_plot.pop(plot_key, None)
        self.plotSeriesChanged.emit(plot_key)

    def set_show_references(self, show: bool) -> None:
        self.show_references = show
        self.visibilityChanged.emit()
