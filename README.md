# TurboPlot — design-iteration results browser (mockup)

A clickable demonstrator of the plotting application described in
[`plotter-app`](plotter-app). It is a real PyQt6 application with a real SQLite
backend and invented-but-plausible results for a 3-stage transonic compressor
front block, built to be shown to users — not a production tool.

## Run it

```bash
uv run python -m turboplot
```

The results database (`results.db`) is generated on first run. Which iterations
are loaded is stored in it, so the app comes back the way you left it. To reset
to the starting state (6 design iterations loaded, 2 reference datasets) and
regenerate the data:

```bash
uv run python -m turboplot --rebuild
```

## What's in the demo data

| | |
|---|---|
| Hardware | CMP-8, 3-stage front block: Rotor 1/2/3, Stator 1/2/3, plus whole-machine results |
| Design iterations | `DES-001` … `DES-014` — 6 loaded at startup, 8 more waiting in the "archive" |
| Reference data | CMP-7B rig test, CMP-7B legacy CFD, HPC-4X competitor benchmark |
| Operating points | Near Stall, Peak Efficiency, Design Point, High Flow (100 % corrected speed) |
| Plots available | 64, built from whatever the database actually contains |

Three kinds of plot, matching the three shapes of result:

- **scalar vs design ID** — e.g. *Rotor 1 → Max Forced Response Strain*; one
  point per design iteration, with reference values drawn as horizontal lines.
- **curve vs operating condition** — e.g. *Whole Machine → Efficiency vs Flow*;
  one curve per design iteration.
- **radial profile** — e.g. *Rotor 1 → Exit Total Pressure Ratio vs Radius*;
  one curve per selected design **and** selected operating point, span on the
  vertical axis.

The demo data has some deliberate stories in it: `DES-004` is a forced-response
regression that blows past the rig-measured strain (open *Rotor 1 → Max Forced
Response Strain*), and reference coverage is partial the way real test data is —
the rig has no stator traverse data, and the competitor benchmark only has
machine-level performance.

## A five-minute walkthrough for users

1. **Open plots from the tree.** Left-hand tree is component → quantity.
   Double-click *Whole Machine → Efficiency vs Flow*. The icons mark the plot
   kind (▪ scalar, ⌒ vs operating condition, ↕ vs radius). Type in the filter
   box to cut the tree down.
2. **Show the new-data behaviour.** Toolbar → *Load design iteration…* → pick
   `DES-007`. It appears on **every open tab** immediately, and on any plot
   opened afterwards. This is the default behaviour asked for in the brief.
3. **Add and remove designs.** Un-tick a design in the left-hand *Design
   iterations* list to take it off every plot. To drop it from one plot only,
   un-tick it in *Series on this plot* on the right; *Follow global* puts that
   plot back in step. Colours belong to a design iteration, so hiding one never
   repaints the others.
4. **Compare against reference data.** *Reference data* checkbox above each
   plot. Rig test, legacy CFD and the benchmark machine are drawn in graphite
   with their own line styles and open markers, so they never look like one more
   design iteration. On a scalar plot they become horizontal reference lines.
5. **Radial profiles at chosen operating points.** Open *Rotor 1 → Exit Total
   Pressure Ratio vs Radius*. The *Operating point* menu multi-selects: with one
   point selected, colour identifies the design; with several, colour is still
   the design and the line style is the operating point.
6. **Read values off the plot.** Hover any curve for a readout. The matplotlib
   toolbar underneath does zoom/pan/save; *Export plot…* (Ctrl+E) writes
   PNG/PDF/SVG.
7. **Hand the plot to someone in Excel.** *Export to Excel…* (Ctrl+Shift+E)
   writes a workbook holding the numbers behind the plot **and** the plot
   itself as a native Excel chart — editable, re-styleable, and re-plottable by
   the recipient without this app. See below.

## Excel export

*Export to Excel…* exports the plot **as it is on screen** — the same series,
the same operating points, the same colours, dash patterns and markers. The
workbook has three sheets:

| Sheet | Contents |
|---|---|
| `Chart` | The chart, as a native Excel chart object. Nothing is a picture. |
| `Data` | The numbers it is drawn from. Scalar plots: one row per design iteration with a column per reference level. Curves and profiles: a column pair (x, y) per series, since each series has its own abscissa. |
| `Info` | What the plot is, which operating points were shown, when it was exported, and a table of every series with its hardware, date, colour and notes. |

Scalar plots export as an Excel line chart over design-ID categories, with one
coloured marker per design iteration and references as flat lines. Curves and
radial profiles export as XY scatter charts, so span stays on the vertical axis
in profile plots exactly as on screen.

Axis ranges come across too, including the tick spacing — left to itself Excel
anchors a value axis at zero, which squashes these quantities into the top of
the plot area. The exported range is the app's, widened to whole tick marks so
the axis labels stay on round numbers (so it can be up to one tick wider than
the app's own view). If the plot is zoomed when you export it, the zoomed view
is what you get.

`.xlsx` is also offered in the ordinary *Export plot…* dialog alongside
PNG/PDF/SVG.

## How it is put together

| File | Role |
|---|---|
| `turboplot/db.py` | Schema and every query the UI makes. No numpy in the UI layer. |
| `turboplot/datagen.py` | Builds the demo database: the invented physics lives here. |
| `turboplot/state.py` | What is loaded, what is visible globally, per-plot overrides; signals that keep every tab in step. |
| `turboplot/plotmodel.py` | A plot described as plain data — what the canvas draws and what the Excel export writes, so the two cannot drift. |
| `turboplot/plotpanel.py` | One plot tab: figure, the three draw routines, hover readout, export. |
| `turboplot/excel_export.py` | Builds the workbook: data sheets plus a native Excel chart. |
| `turboplot/mainwindow.py` | Tree, loaded-data lists, tabs, per-plot series dock. |
| `turboplot/theme.py` | Series colour/style rules and light/dark theming. |
| `turboplot/compat.py` | Clears the macOS hidden flag uv sets on the bundled Qt plugins. |

The plot tree is **derived from the database** (`db.plot_catalog`), not hard
coded — loading hardware with extra instrumentation would grow the tree by
itself.

### Series styling rules

Eight categorical colours, assigned in a fixed order and validated for
colour-vision deficiency. A colour belongs to a design iteration for as long as
it is loaded. A ninth simultaneous design re-uses a hue but switches to a dashed
line, so identity is never carried by colour alone. Reference data sits
deliberately outside that family.

## Known simplifications

- One shaft speed (100 % corrected). Multi-speed maps would add a speed
  selector to the operating-condition plots.
- "Loading" a design iteration reads from the same SQLite file rather than an
  external archive, and is remembered in the `loaded` column.
- No plot layouts/sessions to save, no multi-plot pages, no units switching, no
  user accounts or permissions.
