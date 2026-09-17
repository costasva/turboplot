"""One tab of the plot area: a figure plus the controls that belong to it."""
from __future__ import annotations

import matplotlib
matplotlib.use("QtAgg")

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qtagg import NavigationToolbar2QT as NavigationToolbar
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (QCheckBox, QFileDialog, QHBoxLayout, QLabel, QMenu,
                             QSizePolicy, QToolButton, QVBoxLayout, QWidget)

from . import db
from .state import SessionState


class PlotPanel(QWidget):
    def __init__(self, state: SessionState, spec: db.PlotSpec, parent=None):
        super().__init__(parent)
        self.state = state
        self.spec = spec
        self.show_refs = state.show_references
        self.show_legend = True
        self.op_points = db.op_points_for(state.conn, spec.comp_key, spec.metric_key) \
            if spec.kind == "profile" else []
        # Radial profiles open on the operating point engineers look at first.
        self.selected_ops = [self.op_points[1]] if len(self.op_points) > 1 else list(self.op_points)
        self._hover_index = None
        self._picks: list[tuple[str, np.ndarray, np.ndarray, str]] = []

        self.figure = Figure(figsize=(7.4, 5.0), dpi=100, layout="constrained")
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.ax = self.figure.add_subplot(111)
        self.nav = NavigationToolbar(self.canvas, self)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 4)
        layout.setSpacing(4)
        layout.addLayout(self._build_controls())
        layout.addWidget(self.canvas, 1)
        layout.addWidget(self.nav)

        self.canvas.mpl_connect("motion_notify_event", self._on_hover)
        self.canvas.mpl_connect("figure_leave_event", lambda _e: self._clear_hover())
        self.refresh()

    # -- controls ---------------------------------------------------------
    def _build_controls(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        bar.setSpacing(10)

        if self.spec.kind == "profile":
            self.op_button = QToolButton()
            self.op_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            menu = QMenu(self.op_button)
            self._op_actions = {}
            for op in self.op_points:
                act = QAction(op, menu, checkable=True)
                act.setChecked(op in self.selected_ops)
                act.triggered.connect(lambda checked, o=op: self._toggle_op(o, checked))
                menu.addAction(act)
                self._op_actions[op] = act
            menu.addSeparator()
            all_act = QAction("Select all", menu)
            all_act.triggered.connect(self._select_all_ops)
            menu.addAction(all_act)
            self.op_button.setMenu(menu)
            self._sync_op_button()
            bar.addWidget(QLabel("Operating point:"))
            bar.addWidget(self.op_button)
        bar.addStretch(1)

        self.ref_check = QCheckBox("Reference data")
        self.ref_check.setChecked(self.show_refs)
        self.ref_check.setToolTip("Overlay rig test / legacy CFD / benchmark data on this plot")
        self.ref_check.toggled.connect(self._toggle_refs)
        bar.addWidget(self.ref_check)

        self.legend_check = QCheckBox("Legend")
        self.legend_check.setChecked(True)
        self.legend_check.toggled.connect(self._toggle_legend)
        bar.addWidget(self.legend_check)
        return bar

    def _toggle_op(self, op: str, checked: bool) -> None:
        if checked and op not in self.selected_ops:
            self.selected_ops.append(op)
        elif not checked and op in self.selected_ops:
            if len(self.selected_ops) == 1:          # never leave the plot empty
                self._op_actions[op].setChecked(True)
                return
            self.selected_ops.remove(op)
        self.selected_ops.sort(key=self.op_points.index)
        self._sync_op_button()
        self.refresh()

    def _select_all_ops(self) -> None:
        self.selected_ops = list(self.op_points)
        for op, act in self._op_actions.items():
            act.setChecked(True)
        self._sync_op_button()
        self.refresh()

    def _sync_op_button(self) -> None:
        if len(self.selected_ops) == 1:
            text = self.selected_ops[0]
        elif len(self.selected_ops) == len(self.op_points):
            text = "All operating points"
        else:
            text = f"{self.selected_ops[0]} +{len(self.selected_ops) - 1}"
        self.op_button.setText(f"  {text}  ▾")

    def _toggle_refs(self, on: bool) -> None:
        self.show_refs = on
        self.refresh()

    def _toggle_legend(self, on: bool) -> None:
        self.show_legend = on
        self.refresh()

    def export(self) -> None:
        name = f"{self.spec.comp_key}_{self.spec.metric_key}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Export plot", name,
                                              "PNG image (*.png);;PDF (*.pdf);;SVG (*.svg)")
        if path:
            self.figure.savefig(path, dpi=200)

    # -- drawing ----------------------------------------------------------
    def refresh(self) -> None:
        theme = self.state.theme
        theme.apply_rc(matplotlib.rcParams)
        self.figure.set_facecolor(theme.c["surface"])
        self.ax.clear()
        self.ax.set_facecolor(theme.c["surface"])
        for side in ("top", "right"):
            self.ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            self.ax.spines[side].set_color(theme.c["axis"])
        self.ax.tick_params(colors=theme.c["text_secondary"])
        self._picks.clear()
        self._hover_index = None

        designs, refs = self.state.series_for(self.spec, include_refs=self.show_refs)
        if not designs and not refs:
            self.ax.text(0.5, 0.5, "No series selected for this plot",
                         ha="center", va="center", color=theme.c["muted"],
                         transform=self.ax.transAxes, fontsize=11)
            self.ax.set_xticks([])
            self.ax.set_yticks([])
            self.ax.set_title(self.spec.full_title, color=theme.c["text"])
            self._annotation = None
            self.canvas.draw_idle()
            return

        drawer = {"scalar": self._draw_scalar, "curve": self._draw_curve,
                  "profile": self._draw_profile}[self.spec.kind]
        drawer(designs, refs)

        self.ax.set_title(self.spec.full_title, color=theme.c["text"], pad=10)
        self.ax.grid(True, color=theme.c["grid"], linewidth=0.8)
        self._annotation = self.ax.annotate(
            "", xy=(0, 0), xytext=(11, 11), textcoords="offset points",
            fontsize=8.5, color=theme.c["text"], visible=False, zorder=60,
            bbox=dict(boxstyle="round,pad=0.42", fc=theme.c["surface"],
                      ec=theme.c["axis"], lw=0.8, alpha=0.96),
        )
        self.canvas.draw_idle()

    def _legend(self, handles, labels, extra=None, min_entries=2, **kw):
        if not self.show_legend or not handles or \
                len(handles) + len(extra or []) < min_entries:
            return
        theme = self.state.theme
        ncol = 2 if len(handles) > 8 else 1
        leg = self.ax.legend(handles, labels, ncol=ncol, loc=kw.pop("loc", "best"),
                             borderpad=0.6, labelspacing=0.45, handlelength=2.4,
                             frameon=True)
        for text in leg.get_texts():
            text.set_color(theme.c["text_secondary"])
        leg.get_frame().set_linewidth(0.8)
        if extra:
            self.ax.add_artist(leg)
            leg2 = self.ax.legend(*zip(*extra), loc="lower right", frameon=True,
                                  title="Operating point", borderpad=0.6,
                                  labelspacing=0.4, handlelength=2.4, fontsize=8)
            leg2.get_title().set_color(theme.c["text_secondary"])
            leg2.get_title().set_fontsize(8)
            for text in leg2.get_texts():
                text.set_color(theme.c["text_secondary"])
            leg2.get_frame().set_linewidth(0.8)

    # scalar quantity against design ID ----------------------------------
    def _draw_scalar(self, designs, refs) -> None:
        theme = self.state.theme
        values = db.scalar_values(self.state.conn, self.spec.comp_key, self.spec.metric_key)
        xs = list(range(len(designs)))
        ys = [values[d.source_id] for d in designs]

        if len(xs) > 1:
            self.ax.plot(xs, ys, "-", color=theme.c["axis"], lw=1.4, zorder=2)
        for x, y, d in zip(xs, ys, designs):
            color = theme.design_color(d.color_slot or 0)
            self.ax.plot([x], [y], "o", color=color, markersize=9,
                         markeredgecolor=theme.c["surface"], markeredgewidth=2, zorder=3)
        self._picks.append(("design", np.array(xs, dtype=float), np.array(ys, dtype=float),
                            theme.c["text"]))
        self._pick_labels = [f"{d.source_id}: {v:,.3g}" for d, v in zip(designs, ys)]

        self.ax.set_xticks(xs)
        self.ax.set_xticklabels([d.source_id for d in designs], rotation=35,
                                ha="right", fontsize=8.5)
        self.ax.set_xlim(-0.6, max(len(xs) - 0.4, 0.6))

        handles, labels = [], []
        for ref in refs:
            value = values.get(ref.source_id)
            if value is None:
                continue
            st = self.state.style_for(ref)
            self.ax.axhline(value, color=st.color, linestyle=st.linestyle,
                            linewidth=st.linewidth, zorder=1)
            label = f"{ref.label} ({ref.ref_type})"
            handles.append(Line2D([], [], color=st.color, linestyle=st.linestyle,
                                  linewidth=st.linewidth))
            labels.append(label)
        self.ax.set_xlabel(self.spec.x_label)
        self.ax.set_ylabel(self.spec.y_label)
        self.ax.margins(y=0.14)
        # A single reference line still needs naming, so one entry is enough here.
        self._legend(handles, labels, min_entries=1)

    # quantity against operating condition --------------------------------
    def _draw_curve(self, designs, refs) -> None:
        handles, labels = [], []
        for src in designs + refs:
            x, y = db.curve_series(self.state.conn, self.spec.comp_key,
                                   self.spec.metric_key, src.source_id)
            st = self.state.style_for(src)
            line, = self.ax.plot(x, y, color=st.color, linestyle=st.linestyle,
                                 linewidth=st.linewidth, marker=st.marker,
                                 markersize=st.markersize, fillstyle=st.fillstyle,
                                 markeredgewidth=1.4,
                                 zorder=4 if src.is_design else 3)
            label = src.source_id if src.is_design else f"{src.label} ({src.ref_type})"
            handles.append(line)
            labels.append(label)
            self._picks.append((label, np.asarray(x, float), np.asarray(y, float), st.color))
        self.ax.set_xlabel(self.spec.x_label)
        self.ax.set_ylabel(self.spec.y_label)
        self.ax.margins(x=0.03, y=0.08)
        self._legend(handles, labels)

    # quantity against radius, for selected operating points ---------------
    def _draw_profile(self, designs, refs) -> None:
        theme = self.state.theme
        multi_op = len(self.selected_ops) > 1
        handles, labels = [], []
        for src in designs + refs:
            st = self.state.style_for(src)
            drew_any = False
            for op in self.selected_ops:
                x, y = db.profile_series(self.state.conn, self.spec.comp_key,
                                         self.spec.metric_key, src.source_id, op)
                if not x:
                    continue
                drew_any = True
                ls = theme.op_linestyle(self.selected_ops.index(op)) if multi_op else st.linestyle
                self.ax.plot(x, y, color=st.color, linestyle=ls, linewidth=st.linewidth,
                             marker=st.marker if not src.is_design else "",
                             markersize=st.markersize, fillstyle=st.fillstyle,
                             markeredgewidth=1.3, zorder=4 if src.is_design else 3)
                label = f"{src.source_id if src.is_design else src.label} — {op}"
                self._picks.append((label, np.asarray(x, float), np.asarray(y, float), st.color))
            if drew_any:
                handles.append(Line2D([], [], color=st.color, linewidth=st.linewidth,
                                      linestyle="-" if multi_op else st.linestyle,
                                      marker="" if src.is_design else st.marker,
                                      fillstyle=st.fillstyle, markersize=st.markersize))
                labels.append(src.source_id if src.is_design else f"{src.label} ({src.ref_type})")

        extra = None
        if multi_op:
            extra = [(Line2D([], [], color=theme.c["text_secondary"], linewidth=1.8,
                             linestyle=theme.op_linestyle(self.selected_ops.index(op))), op)
                     for op in self.selected_ops]
        # Radial results are read with span on the vertical axis.
        self.ax.set_xlabel(self.spec.y_label)
        self.ax.set_ylabel(self.spec.x_label)
        self.ax.margins(x=0.06)
        self.ax.set_ylim(0, 1)
        self.ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        self.ax.set_yticklabels(["0.0\nhub", "0.25", "0.50", "0.75", "1.0\ntip"])
        self._legend(handles, labels, extra=extra, loc="upper left")

    # -- hover readout -----------------------------------------------------
    def _on_hover(self, event) -> None:
        if event.inaxes is not self.ax or not self._picks or self._annotation is None:
            self._clear_hover()
            return
        xr = self.ax.get_xlim()
        yr = self.ax.get_ylim()
        sx = (xr[1] - xr[0]) or 1.0
        sy = (yr[1] - yr[0]) or 1.0
        best = None
        for si, (label, xs, ys, color) in enumerate(self._picks):
            if len(xs) == 0:
                continue
            d = ((xs - event.xdata) / sx) ** 2 + ((ys - event.ydata) / sy) ** 2
            i = int(np.argmin(d))
            if best is None or d[i] < best[0]:
                best = (d[i], si, i, label, xs[i], ys[i], color)
        if best is None or best[0] > 0.0016:      # ~4 % of the axes away
            self._clear_hover()
            return
        _, si, i, label, x, y, color = best
        if self._hover_index == (si, i):
            return
        self._hover_index = (si, i)
        if self.spec.kind == "scalar":
            text = self._pick_labels[i]
        elif self.spec.kind == "profile":
            text = f"{label}\n{self.spec.y_label.split(' (')[0]}: {x:,.4g}\nSpan: {y:.2f}"
        else:
            text = f"{label}\n{x:,.4g} → {y:,.4g}"
        self._annotation.xy = (x, y)
        self._annotation.set_text(text)
        self._annotation.set_color(self.state.theme.c["text"])
        self._annotation.set_visible(True)
        self.canvas.draw_idle()

    def _clear_hover(self) -> None:
        if getattr(self, "_annotation", None) is not None and self._annotation.get_visible():
            self._annotation.set_visible(False)
            self._hover_index = None
            self.canvas.draw_idle()
