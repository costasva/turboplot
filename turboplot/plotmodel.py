"""A plot described as plain data, independent of how it gets drawn.

`PlotPanel.plot_data()` builds one of these from what the user has selected;
matplotlib draws it on screen and the Excel export writes the same thing to a
workbook, so the two can never drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .db import Source


@dataclass(frozen=True)
class Series:
    source: Source
    op: str | None                    # operating point, for radial profiles
    x: list[float] = field(default_factory=list)
    y: list[float] = field(default_factory=list)
    value: float | None = None        # the single number, for scalar plots

    @property
    def name(self) -> str:
        return self.source.source_id if self.source.is_design else self.source.label

    @property
    def label(self) -> str:
        """How this series is named on a legend or a worksheet column."""
        if self.op:
            return f"{self.name} — {self.op}"
        if not self.source.is_design:
            return f"{self.name} ({self.source.ref_type})"
        return self.name


@dataclass(frozen=True)
class PlotData:
    kind: str                         # 'scalar' | 'curve' | 'profile'
    series: list[Series]
    refs: list[Series]                # scalar plots only: reference levels
    ops: list[str]                    # profile plots only: operating points shown

    @property
    def is_empty(self) -> bool:
        return not self.series and not self.refs
