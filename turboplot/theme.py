"""Colour and style rules for every series the app draws.

Rules that the plots are built to keep:
  * A colour belongs to a design iteration, not to its position in a list.
    Hiding DES-002 never repaints DES-003.
  * Eight categorical hues, assigned in fixed order, never cycled into new
    hues.  A ninth simultaneous design re-uses a hue but changes line style,
    so identity is never carried by colour alone.
  * Reference data is deliberately outside the categorical family: graphite
    tones with their own line styles and open markers, so a test curve never
    looks like one more design iteration.
"""
from __future__ import annotations

from dataclasses import dataclass

# Validated categorical palette (adjacent-pair CVD safe in both modes).
SERIES_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
SERIES_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500",
               "#d55181", "#008300", "#9085e9", "#e66767"]

LIGHT = dict(
    surface="#fcfcfb", panel="#f3f2ef", text="#0b0b0b", text_secondary="#52514e",
    muted="#8a8880", grid="#e2e1dd", axis="#b8b6b0", series=SERIES_LIGHT,
    ref=["#3d3c39", "#7b7974", "#0b0b0b"], band="#e8e7e3",
)
DARK = dict(
    surface="#1a1a19", panel="#232322", text="#ffffff", text_secondary="#c3c2b7",
    muted="#8f8e86", grid="#343432", axis="#4d4c49", series=SERIES_DARK,
    ref=["#d6d5cc", "#9a998f", "#ffffff"], band="#2a2a28",
)

REF_LINESTYLES = [(0, (6, 3)), (0, (7, 2, 1.5, 2)), (0, (1.5, 2.5))]
REF_MARKERS = ["s", "^", "D"]
OP_LINESTYLES = ["-", (0, (5, 2.5)), (0, (6, 2, 1, 2)), (0, (1.5, 2))]

# The same styles named for Excel, so an exported chart looks like the plot.
DESIGN_DASHES = ["solid", "dash", "sysDot"]
REF_DASHES = ["dash", "dashDot", "sysDot"]
REF_SYMBOLS = ["square", "triangle", "diamond"]
OP_DASHES = ["solid", "dash", "dashDot", "sysDot"]


@dataclass(frozen=True)
class SeriesStyle:
    color: str
    linestyle: object
    marker: str
    linewidth: float
    markersize: float
    fillstyle: str = "full"
    dash: str = "solid"          # the same line style, named for Excel
    symbol: str = "circle"       # the same marker, named for Excel

    @property
    def rgb(self) -> str:
        return self.color.lstrip("#").upper()


class Theme:
    def __init__(self, dark: bool = False):
        self.set_dark(dark)

    def set_dark(self, dark: bool) -> None:
        self.dark = dark
        self.c = DARK if dark else LIGHT

    # -- styles -----------------------------------------------------------
    def design_style(self, color_slot: int) -> SeriesStyle:
        palette = self.c["series"]
        color = palette[color_slot % len(palette)]
        wrap = color_slot // len(palette)
        # Second time round the palette, line style carries the identity.
        ls = ["-", (0, (5, 2)), (0, (1, 1.6))][min(wrap, 2)]
        return SeriesStyle(color=color, linestyle=ls, marker="o",
                           linewidth=2.0, markersize=4.6,
                           dash=DESIGN_DASHES[min(wrap, 2)], symbol="circle")

    def design_color(self, color_slot: int) -> str:
        return self.c["series"][color_slot % len(self.c["series"])]

    def reference_style(self, index: int) -> SeriesStyle:
        return SeriesStyle(
            color=self.c["ref"][index % len(self.c["ref"])],
            linestyle=REF_LINESTYLES[index % len(REF_LINESTYLES)],
            marker=REF_MARKERS[index % len(REF_MARKERS)],
            linewidth=1.9, markersize=5.4, fillstyle="none",
            dash=REF_DASHES[index % len(REF_DASHES)],
            symbol=REF_SYMBOLS[index % len(REF_SYMBOLS)],
        )

    def op_linestyle(self, index: int):
        return OP_LINESTYLES[index % len(OP_LINESTYLES)]

    def op_dash(self, index: int) -> str:
        return OP_DASHES[index % len(OP_DASHES)]

    # -- matplotlib -------------------------------------------------------
    def apply_rc(self, rcParams) -> None:
        c = self.c
        rcParams.update({
            "figure.facecolor": c["surface"],
            "axes.facecolor": c["surface"],
            "savefig.facecolor": c["surface"],
            "axes.edgecolor": c["axis"],
            "axes.labelcolor": c["text_secondary"],
            "axes.titlecolor": c["text"],
            "axes.titlesize": 11,
            "axes.titleweight": "medium",
            "axes.labelsize": 9.5,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": c["grid"],
            "grid.linewidth": 0.8,
            "xtick.color": c["text_secondary"],
            "ytick.color": c["text_secondary"],
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "text.color": c["text"],
            "legend.fontsize": 8.5,
            "legend.framealpha": 0.92,
            "legend.facecolor": c["surface"],
            "legend.edgecolor": c["grid"],
            "font.size": 9.5,
            "lines.solid_capstyle": "round",
            "lines.dash_capstyle": "round",
        })


def qt_stylesheet(theme: Theme) -> str:
    c = theme.c
    base = f"""
    QMainWindow, QDialog {{ background: {c['panel']}; }}
    QWidget {{ color: {c['text']}; }}
    QTreeWidget, QListWidget, QTextEdit, QTableWidget {{
        background: {c['surface']}; border: 1px solid {c['grid']};
        selection-background-color: {c['series'][0]}; selection-color: #ffffff;
    }}
    QTreeWidget::item, QListWidget::item {{ padding: 2px 1px; }}
    QDockWidget {{ color: {c['text_secondary']}; }}
    QDockWidget::title {{ background: {c['panel']}; padding: 5px 8px;
        font-weight: 600; border-bottom: 1px solid {c['grid']}; }}
    QTabWidget::pane {{ border: 1px solid {c['grid']}; background: {c['surface']}; }}
    QTabBar::tab {{ background: {c['panel']}; padding: 6px 12px;
        border: 1px solid {c['grid']}; border-bottom: none; margin-right: 2px; }}
    QTabBar::tab:selected {{ background: {c['surface']}; color: {c['text']}; }}
    QStatusBar {{ background: {c['panel']}; color: {c['text_secondary']}; }}
    QToolBar {{ background: {c['panel']}; border-bottom: 1px solid {c['grid']};
        spacing: 4px; padding: 3px; }}
    QLabel#hint, QLabel#sectionNote {{ color: {c['text_secondary']}; }}
    QLabel#sectionNote {{ font-size: 11px; }}
    """
    if not theme.dark:
        return base
    # Native macOS controls stay light under a dark canvas, so they are styled
    # explicitly here rather than left to the platform.
    return base + f"""
    QPushButton, QToolButton {{
        background: {c['panel']}; color: {c['text']};
        border: 1px solid {c['axis']}; border-radius: 4px; padding: 4px 10px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {c['grid']}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c['axis']}; }}
    QPushButton:disabled {{ color: {c['muted']}; border-color: {c['grid']}; }}
    QToolBar QToolButton {{ border: none; background: transparent; }}
    QToolBar QToolButton:hover {{ background: {c['grid']}; border-radius: 4px; }}
    QLineEdit {{ background: {c['surface']}; color: {c['text']};
        border: 1px solid {c['axis']}; border-radius: 4px; padding: 3px 6px;
        selection-background-color: {c['series'][0]}; }}
    QMenu {{ background: {c['panel']}; color: {c['text']};
        border: 1px solid {c['axis']}; }}
    QMenu::item:selected {{ background: {c['series'][0]}; color: #ffffff; }}
    QScrollBar:vertical, QScrollBar:horizontal {{ background: {c['panel']}; border: none; }}
    QScrollBar::handle {{ background: {c['axis']}; border-radius: 4px; }}
    QMessageBox {{ background: {c['panel']}; }}
    QHeaderView::section {{ background: {c['panel']}; color: {c['text_secondary']}; }}
    """
