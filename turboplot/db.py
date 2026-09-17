"""SQLite backend for the results store.

The mockup keeps every result in a single SQLite file so the UI can be written
against the same query patterns a production (Postgres/Oracle) backend would
use.  Nothing in the UI touches numpy arrays directly -- it asks this module.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "results.db"

SCHEMA = """
PRAGMA foreign_keys = ON;

-- A "source" is anything that can appear as a series on a plot: either a
-- design iteration of the hardware under development, or reference data.
CREATE TABLE sources (
    source_id   TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('design', 'reference')),
    label       TEXT NOT NULL,
    sort_key    INTEGER NOT NULL,
    hardware    TEXT,
    created     TEXT,
    ref_type    TEXT,               -- 'Rig test', 'CFD', ... (reference only)
    notes       TEXT,
    loaded      INTEGER NOT NULL DEFAULT 0,
    color_slot  INTEGER             -- assigned on load, sticks to the entity
);

CREATE TABLE components (
    comp_key    TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    comp_type   TEXT NOT NULL,      -- 'machine' | 'rotor' | 'stator'
    sort_key    INTEGER NOT NULL
);

-- Metadata for every quantity we can plot: drives axis labels and plot titles.
CREATE TABLE metrics (
    metric_key  TEXT PRIMARY KEY,
    kind        TEXT NOT NULL CHECK (kind IN ('scalar', 'curve', 'profile')),
    title       TEXT NOT NULL,      -- short name shown in the plot tree
    y_label     TEXT NOT NULL,
    x_label     TEXT NOT NULL,
    units       TEXT,
    sort_key    INTEGER NOT NULL
);

-- One number per (source, component): plotted against design ID.
CREATE TABLE scalars (
    source_id   TEXT NOT NULL REFERENCES sources(source_id),
    comp_key    TEXT NOT NULL REFERENCES components(comp_key),
    metric_key  TEXT NOT NULL REFERENCES metrics(metric_key),
    value       REAL NOT NULL,
    PRIMARY KEY (source_id, comp_key, metric_key)
);

-- Quantity swept over operating condition (corrected flow along a speedline).
CREATE TABLE curve_points (
    source_id   TEXT NOT NULL REFERENCES sources(source_id),
    comp_key    TEXT NOT NULL REFERENCES components(comp_key),
    metric_key  TEXT NOT NULL REFERENCES metrics(metric_key),
    speed_pct   REAL NOT NULL,
    x           REAL NOT NULL,      -- corrected flow, kg/s
    y           REAL NOT NULL
);
CREATE INDEX ix_curve ON curve_points (comp_key, metric_key, source_id);

-- Quantity varying with radius at a machine station, for a named operating point.
CREATE TABLE profile_points (
    source_id    TEXT NOT NULL REFERENCES sources(source_id),
    comp_key     TEXT NOT NULL REFERENCES components(comp_key),
    metric_key   TEXT NOT NULL REFERENCES metrics(metric_key),
    op_point     TEXT NOT NULL,     -- 'Peak Efficiency', 'Near Stall', ...
    radius_frac  REAL NOT NULL,     -- 0 = hub, 1 = tip
    value        REAL NOT NULL
);
CREATE INDEX ix_profile ON profile_points (comp_key, metric_key, op_point, source_id);

-- Ordering of the named operating points, worst flow to highest flow.
CREATE TABLE op_points (
    op_point    TEXT PRIMARY KEY,
    sort_key    INTEGER NOT NULL
);
"""


@dataclass(frozen=True)
class Source:
    source_id: str
    kind: str
    label: str
    sort_key: int
    hardware: str
    created: str
    ref_type: str | None
    notes: str
    loaded: bool
    color_slot: int | None

    @property
    def is_design(self) -> bool:
        return self.kind == "design"


@dataclass(frozen=True)
class PlotSpec:
    """One leaf of the plot tree: a (component, metric) pair that has data."""
    comp_key: str
    comp_name: str
    metric_key: str
    kind: str
    title: str
    x_label: str
    y_label: str

    @property
    def key(self) -> str:
        return f"{self.comp_key}::{self.metric_key}"

    @property
    def full_title(self) -> str:
        return f"{self.comp_name} — {self.title}"


def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _row_to_source(row: sqlite3.Row) -> Source:
    return Source(
        source_id=row["source_id"],
        kind=row["kind"],
        label=row["label"],
        sort_key=row["sort_key"],
        hardware=row["hardware"],
        created=row["created"],
        ref_type=row["ref_type"],
        notes=row["notes"],
        loaded=bool(row["loaded"]),
        color_slot=row["color_slot"],
    )


def sources(conn: sqlite3.Connection, kind: str, loaded: bool | None = None) -> list[Source]:
    sql = "SELECT * FROM sources WHERE kind = ?"
    args: list = [kind]
    if loaded is not None:
        sql += " AND loaded = ?"
        args.append(int(loaded))
    sql += " ORDER BY sort_key"
    return [_row_to_source(r) for r in conn.execute(sql, args)]


def set_loaded(conn: sqlite3.Connection, source_id: str, loaded: bool, color_slot: int | None = None) -> None:
    conn.execute(
        "UPDATE sources SET loaded = ?, color_slot = COALESCE(?, color_slot) WHERE source_id = ?",
        (int(loaded), color_slot, source_id),
    )
    conn.commit()


def plot_catalog(conn: sqlite3.Connection) -> list[PlotSpec]:
    """Every (component, metric) pair that has data for at least one source.

    The plot tree in the UI is built from this, so loading new hardware with
    extra instrumentation would grow the tree by itself.
    """
    sql = """
        SELECT DISTINCT comp_key, metric_key FROM scalars
        UNION SELECT DISTINCT comp_key, metric_key FROM curve_points
        UNION SELECT DISTINCT comp_key, metric_key FROM profile_points
    """
    comps = {r["comp_key"]: r for r in conn.execute("SELECT * FROM components")}
    mets = {r["metric_key"]: r for r in conn.execute("SELECT * FROM metrics")}
    specs = []
    for row in conn.execute(sql):
        c, m = comps[row["comp_key"]], mets[row["metric_key"]]
        specs.append(
            PlotSpec(
                comp_key=c["comp_key"],
                comp_name=c["name"],
                metric_key=m["metric_key"],
                kind=m["kind"],
                title=m["title"],
                x_label=m["x_label"],
                y_label=m["y_label"],
            )
        )
    specs.sort(key=lambda s: (comps[s.comp_key]["sort_key"], mets[s.metric_key]["sort_key"]))
    return specs


def op_points_for(conn: sqlite3.Connection, comp_key: str, metric_key: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT p.op_point, o.sort_key FROM profile_points p
        JOIN op_points o USING (op_point)
        WHERE p.comp_key = ? AND p.metric_key = ?
        ORDER BY o.sort_key
        """,
        (comp_key, metric_key),
    )
    return [r["op_point"] for r in rows]


def scalar_values(conn: sqlite3.Connection, comp_key: str, metric_key: str) -> dict[str, float]:
    rows = conn.execute(
        "SELECT source_id, value FROM scalars WHERE comp_key = ? AND metric_key = ?",
        (comp_key, metric_key),
    )
    return {r["source_id"]: r["value"] for r in rows}


def curve_series(conn: sqlite3.Connection, comp_key: str, metric_key: str,
                 source_id: str) -> tuple[list[float], list[float]]:
    rows = conn.execute(
        """SELECT x, y FROM curve_points
           WHERE comp_key = ? AND metric_key = ? AND source_id = ? ORDER BY x""",
        (comp_key, metric_key, source_id),
    ).fetchall()
    return [r["x"] for r in rows], [r["y"] for r in rows]


def profile_series(conn: sqlite3.Connection, comp_key: str, metric_key: str,
                   source_id: str, op_point: str) -> tuple[list[float], list[float]]:
    rows = conn.execute(
        """SELECT radius_frac, value FROM profile_points
           WHERE comp_key = ? AND metric_key = ? AND source_id = ? AND op_point = ?
           ORDER BY radius_frac""",
        (comp_key, metric_key, source_id, op_point),
    ).fetchall()
    return [r["value"] for r in rows], [r["radius_frac"] for r in rows]


def sources_with_data(conn: sqlite3.Connection, spec: PlotSpec) -> set[str]:
    table = {"scalar": "scalars", "curve": "curve_points", "profile": "profile_points"}[spec.kind]
    rows = conn.execute(
        f"SELECT DISTINCT source_id FROM {table} WHERE comp_key = ? AND metric_key = ?",
        (spec.comp_key, spec.metric_key),
    )
    return {r["source_id"] for r in rows}
