"""Builds the demo results database.

Everything here is invented but shaped like real 3-stage transonic compressor
results: speedlines that flatten toward stall and fall off into choke, radial
profiles with hub/tip endwall deficits, a forced-response strain outlier, and
reference data that only covers part of the matrix (as rig data always does).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from . import db

RNG = np.random.default_rng(20260917)

COMPONENTS = [
    ("machine", "Whole Machine", "machine", 0),
    ("r1", "Rotor 1", "rotor", 1),
    ("s1", "Stator 1", "stator", 2),
    ("r2", "Rotor 2", "rotor", 3),
    ("s2", "Stator 2", "stator", 4),
    ("r3", "Rotor 3", "rotor", 5),
    ("s3", "Stator 3", "stator", 6),
]

OP_POINTS = ["Near Stall", "Peak Efficiency", "Design Point", "High Flow"]
# Position of each named operating point along the speedline (0 = stall, 1 = choke)
OP_FRAC = {"Near Stall": 0.08, "Peak Efficiency": 0.45, "Design Point": 0.62, "High Flow": 0.88}

FLOW_LO, FLOW_HI = 37.5, 45.5   # kg/s corrected, 100 % speed

# metric_key, kind, title, y_label, x_label, units, sort_key
METRICS = [
    # --- scalar, plotted against design ID -------------------------------
    ("poly_eff",     "scalar", "Peak Polytropic Efficiency", "Polytropic efficiency (%)", "Design iteration", "%", 10),
    ("design_pr",    "scalar", "Pressure Ratio at Design Point", "Total pressure ratio (–)", "Design iteration", "", 11),
    ("surge_margin", "scalar", "Surge Margin", "Surge margin (%)", "Design iteration", "%", 12),
    ("design_flow",  "scalar", "Corrected Flow at Design Point", "Corrected flow (kg/s)", "Design iteration", "kg/s", 13),
    ("weight",       "scalar", "Rotating Assembly Weight", "Weight (kg)", "Design iteration", "kg", 14),
    ("peak_eff",     "scalar", "Peak Stage Efficiency", "Isentropic efficiency (%)", "Design iteration", "%", 15),
    ("max_stress",   "scalar", "Max Von Mises Stress", "Max von Mises stress (MPa)", "Design iteration", "MPa", 16),
    ("max_strain",   "scalar", "Max Forced Response Strain", "Peak alternating strain (µε)", "Design iteration", "µε", 17),
    ("freq_margin",  "scalar", "1F Frequency Margin", "Frequency margin (%)", "Design iteration", "%", 18),
    ("min_loss",     "scalar", "Minimum Loss Coefficient", "Total pressure loss coefficient (–)", "Design iteration", "", 19),
    # --- curves against operating condition -------------------------------
    ("pr_vs_flow",       "curve", "Pressure Ratio vs Flow", "Total pressure ratio (–)", "Corrected flow (kg/s)", "", 30),
    ("eff_vs_flow",      "curve", "Efficiency vs Flow", "Polytropic efficiency (%)", "Corrected flow (kg/s)", "%", 31),
    ("stage_pr_vs_flow", "curve", "Stage Pressure Ratio vs Flow", "Stage total pressure ratio (–)", "Corrected flow (kg/s)", "", 32),
    ("stage_eff_vs_flow","curve", "Stage Efficiency vs Flow", "Isentropic efficiency (%)", "Corrected flow (kg/s)", "%", 33),
    ("incidence_vs_flow","curve", "Incidence vs Flow", "Mid-span incidence (deg)", "Corrected flow (kg/s)", "deg", 34),
    ("loss_vs_flow",     "curve", "Loss Coefficient vs Flow", "Total pressure loss coefficient (–)", "Corrected flow (kg/s)", "", 35),
    ("swirl_vs_flow",    "curve", "Exit Swirl vs Flow", "Exit swirl angle (deg)", "Corrected flow (kg/s)", "deg", 36),
    # --- radial profiles ---------------------------------------------------
    ("exit_pt_ratio",  "profile", "Exit Total Pressure Ratio vs Radius", "Total pressure ratio (–)", "Span fraction (hub → tip)", "", 50),
    ("exit_tt_ratio",  "profile", "Exit Total Temperature Ratio vs Radius", "Total temperature ratio (–)", "Span fraction (hub → tip)", "", 51),
    ("exit_alpha",     "profile", "Exit Flow Angle vs Radius", "Absolute flow angle (deg)", "Span fraction (hub → tip)", "deg", 52),
    ("exit_mach_rel",  "profile", "Exit Relative Mach vs Radius", "Relative Mach number (–)", "Span fraction (hub → tip)", "", 53),
    ("exit_mach",      "profile", "Exit Mach Number vs Radius", "Absolute Mach number (–)", "Span fraction (hub → tip)", "", 54),
    ("exit_loss",      "profile", "Exit Loss Coefficient vs Radius", "Total pressure loss coefficient (–)", "Span fraction (hub → tip)", "", 55),
]

# Which plots exist for each component type.
PLOTS_BY_TYPE = {
    "machine": {
        "scalar": ["poly_eff", "design_pr", "surge_margin", "design_flow", "weight"],
        "curve": ["pr_vs_flow", "eff_vs_flow"],
        "profile": ["exit_pt_ratio", "exit_tt_ratio", "exit_alpha"],
    },
    "rotor": {
        "scalar": ["peak_eff", "max_stress", "max_strain", "freq_margin"],
        "curve": ["stage_pr_vs_flow", "stage_eff_vs_flow", "incidence_vs_flow"],
        "profile": ["exit_pt_ratio", "exit_tt_ratio", "exit_alpha", "exit_mach_rel"],
    },
    "stator": {
        "scalar": ["min_loss", "max_stress"],
        "curve": ["loss_vs_flow", "swirl_vs_flow"],
        "profile": ["exit_loss", "exit_mach", "exit_alpha"],
    },
}

STAGE_SHARE = {"r1": 0.42, "r2": 0.34, "r3": 0.24}     # share of overall work
STAGE_INDEX = {"r1": 0, "s1": 0, "r2": 1, "s2": 1, "r3": 2, "s3": 2}


class DesignTraits:
    """Per-design scalar knobs that every generated result is derived from."""

    def __init__(self, idx: int, source_id: str):
        self.idx = idx
        self.source_id = source_id
        j = RNG.normal(0, 1, 8)
        # Efficiency climbs through the programme, with a regression at DES-004.
        self.eff_peak = 88.4 + 2.1 * (1 - np.exp(-idx / 3.2)) + 0.12 * j[0]
        if idx == 3:
            self.eff_peak -= 0.85                      # the restagger that went backwards
        self.pr_peak = 5.02 + 0.045 * idx + 0.02 * j[1]
        self.flow_shift = 0.35 * np.tanh(idx / 4) + 0.08 * j[2]
        self.surge_margin = 17.5 + 1.4 * np.tanh((idx - 2) / 2.5) + 0.35 * j[3]
        self.stress_scale = 1.0 + 0.035 * j[4] - 0.012 * idx
        self.strain_scale = 1.0 + 0.08 * j[5]
        if idx == 3:
            self.strain_scale = 1.62                   # blade that rang on the rig
        self.weight = 214.0 - 1.9 * idx + 1.2 * j[6]
        self.tip_loading = 0.0 + 0.06 * j[7] - 0.02 * idx


def flow_grid(traits: DesignTraits | None = None, n: int = 14) -> np.ndarray:
    shift = traits.flow_shift if traits else 0.0
    return np.linspace(FLOW_LO + shift, FLOW_HI + shift, n)


def _x_norm(flow: np.ndarray, traits: DesignTraits | None) -> np.ndarray:
    shift = traits.flow_shift if traits else 0.0
    return np.clip((flow - FLOW_LO - shift) / (FLOW_HI - FLOW_LO), 0.0, 1.0)


def machine_pr(flow, traits, noise=0.0):
    x = _x_norm(flow, traits)
    pr = traits.pr_peak * (1 - 0.185 * x ** 2.6) - 0.012 * x
    return pr + noise * RNG.normal(0, 1, np.shape(flow))


def machine_eff(flow, traits, noise=0.0):
    x = _x_norm(flow, traits)
    eff = traits.eff_peak - 11.5 * (x - 0.45) ** 2 - 6.0 * np.clip(x - 0.8, 0, None) ** 2 * 10
    return eff + noise * RNG.normal(0, 1, np.shape(flow))


def stage_pr(flow, traits, comp, noise=0.0):
    share = STAGE_SHARE[comp]
    overall = machine_pr(flow, traits)
    return overall ** share + noise * RNG.normal(0, 1, np.shape(flow))


def stage_eff(flow, traits, comp, noise=0.0):
    x = _x_norm(flow, traits)
    offset = {"r1": 1.2, "r2": 0.2, "r3": -0.9}[comp]
    peak_shift = {"r1": 0.40, "r2": 0.47, "r3": 0.55}[comp]
    eff = traits.eff_peak + offset - 13.0 * (x - peak_shift) ** 2
    return eff + noise * RNG.normal(0, 1, np.shape(flow))


def incidence(flow, traits, comp, noise=0.0):
    x = _x_norm(flow, traits)
    return (6.5 - 11.0 * x) - 1.1 * STAGE_INDEX[comp] + noise * RNG.normal(0, 1, np.shape(flow))


def stator_loss(flow, traits, comp, noise=0.0):
    x = _x_norm(flow, traits)
    base = 0.030 + 0.006 * STAGE_INDEX[comp] - 0.0015 * traits.idx
    return base + 0.075 * (x - 0.42) ** 2 + 0.05 * np.clip(x - 0.82, 0, None) ** 2 * 12 \
        + noise * RNG.normal(0, 1, np.shape(flow))


def stator_swirl(flow, traits, comp, noise=0.0):
    x = _x_norm(flow, traits)
    return 3.0 + 14.0 * x + 1.5 * STAGE_INDEX[comp] + noise * RNG.normal(0, 1, np.shape(flow))


def _endwall(r: np.ndarray, hub_depth: float, tip_depth: float) -> np.ndarray:
    """Multiplicative hub/tip deficit that decays into the free stream."""
    return 1.0 - hub_depth * np.exp(-(r / 0.13) ** 2) - tip_depth * np.exp(-((1 - r) / 0.11) ** 2)


def profile_values(metric, comp, comp_type, traits, op_frac, r):
    stage = STAGE_INDEX.get(comp, 0)
    if metric == "exit_pt_ratio":
        if comp_type == "machine":
            base = machine_pr(np.array([FLOW_LO + op_frac * (FLOW_HI - FLOW_LO)]), traits)[0]
        else:
            base = stage_pr(np.array([FLOW_LO + op_frac * (FLOW_HI - FLOW_LO)]), traits, comp)[0]
        shape = 1.0 + (0.035 + traits.tip_loading) * (r - 0.5)
        return base * shape * _endwall(r, 0.055 + 0.02 * op_frac, 0.075 + 0.05 * op_frac)
    if metric == "exit_tt_ratio":
        work = {"machine": 1.62, "rotor": 1.0 + 0.22 * STAGE_SHARE.get(comp, 0.3)}.get(comp_type, 1.18)
        if comp_type == "rotor":
            work = 1.0 + 0.62 * STAGE_SHARE[comp]
        shape = 1.0 + 0.018 * (0.5 - r) + 0.012 * traits.tip_loading
        return work * shape * (1 + 0.012 * np.exp(-((1 - r) / 0.10) ** 2))
    if metric == "exit_alpha":
        base = 33.0 + 12.0 * r + 6.0 * (0.5 - op_frac) + 2.0 * stage
        return base + 4.5 * np.exp(-((1 - r) / 0.09) ** 2) - 3.0 * np.exp(-(r / 0.10) ** 2)
    if metric == "exit_mach_rel":
        base = 0.76 + 0.42 * r + 0.10 * op_frac - 0.05 * stage
        return base * _endwall(r, 0.06, 0.05) + 0.02 * traits.tip_loading
    if metric == "exit_mach":
        base = 0.58 + 0.10 * r + 0.14 * op_frac - 0.04 * stage
        return base * _endwall(r, 0.09, 0.08)
    if metric == "exit_loss":
        base = 0.026 + 0.006 * stage + 0.03 * (op_frac - 0.45) ** 2
        return base + 0.085 * np.exp(-(r / 0.12) ** 2) + 0.11 * np.exp(-((1 - r) / 0.10) ** 2) \
            + 0.010 * traits.tip_loading
    raise KeyError(metric)


def scalar_value(metric, comp, comp_type, traits):
    if metric == "poly_eff":
        return traits.eff_peak
    if metric == "design_pr":
        return machine_pr(np.array([FLOW_LO + 0.62 * (FLOW_HI - FLOW_LO)]), traits)[0]
    if metric == "surge_margin":
        return traits.surge_margin
    if metric == "design_flow":
        return FLOW_LO + traits.flow_shift + 0.62 * (FLOW_HI - FLOW_LO)
    if metric == "weight":
        return traits.weight
    if metric == "peak_eff":
        return float(np.max(stage_eff(flow_grid(traits, 60), traits, comp)))
    if metric == "max_stress":
        base = {"rotor": [742, 690, 655], "stator": [268, 245, 231]}[comp_type][STAGE_INDEX[comp]]
        return base * traits.stress_scale
    if metric == "max_strain":
        base = [118, 96, 88][STAGE_INDEX[comp]]
        return base * traits.strain_scale
    if metric == "freq_margin":
        return 21.0 + 3.5 * np.tanh((traits.idx - 1) / 3) - 2.0 * STAGE_INDEX[comp] \
            - (6.0 if traits.idx == 3 and comp == "r1" else 0.0)
    if metric == "min_loss":
        return float(np.min(stator_loss(flow_grid(traits, 60), traits, comp)))
    raise KeyError(metric)


def curve_values(metric, comp, traits, flow, noise=0.0):
    if metric == "pr_vs_flow":
        return machine_pr(flow, traits, noise * 0.01)
    if metric == "eff_vs_flow":
        return machine_eff(flow, traits, noise * 0.15)
    if metric == "stage_pr_vs_flow":
        return stage_pr(flow, traits, comp, noise * 0.008)
    if metric == "stage_eff_vs_flow":
        return stage_eff(flow, traits, comp, noise * 0.2)
    if metric == "incidence_vs_flow":
        return incidence(flow, traits, comp, noise * 0.15)
    if metric == "loss_vs_flow":
        return stator_loss(flow, traits, comp, noise * 0.0015)
    if metric == "swirl_vs_flow":
        return stator_swirl(flow, traits, comp, noise * 0.3)
    raise KeyError(metric)


# --------------------------------------------------------------------------
# Reference datasets.  Coverage is deliberately partial.
# --------------------------------------------------------------------------
REFERENCES = [
    dict(source_id="RIG-CMP7B", label="CMP-7B Rig Test", ref_type="Rig test",
         hardware="CMP-7B build 2", created="2025-11-08",
         notes="Cell 4 rig test, 100 % corrected speed. Radial traverses at two "
               "operating points; strain gauges on R1 and R2.",
         traits_idx=2, noise=1.0, comps=["machine", "r1", "r2", "s1"],
         profile_ops=["Peak Efficiency", "Design Point"], n_radial=9,
         scalars=[("machine", "poly_eff"), ("machine", "surge_margin"),
                  ("r1", "max_strain"), ("r2", "max_strain"), ("r1", "max_stress")]),
    dict(source_id="CFD-CMP7B", label="CMP-7B CFD (legacy)", ref_type="CFD",
         hardware="CMP-7B build 2", created="2025-06-21",
         notes="Legacy steady RANS of the tested build, run with the previous "
               "turbulence model settings. Full matrix.",
         traits_idx=2, noise=0.15, comps=[c[0] for c in COMPONENTS],
         profile_ops=OP_POINTS, n_radial=21,
         scalars=[("machine", "poly_eff"), ("machine", "design_pr"),
                  ("machine", "surge_margin"), ("r1", "peak_eff"), ("r1", "max_stress")]),
    dict(source_id="HPC-4X", label="HPC-4X (competitor teardown)", ref_type="Benchmark",
         hardware="HPC-4X stage 1-3", created="2024-09-30",
         notes="Scaled benchmark for a similar-class 3-stage front block. "
               "Machine-level performance only.",
         traits_idx=0, noise=0.4, comps=["machine"],
         profile_ops=["Peak Efficiency"], n_radial=15,
         scalars=[("machine", "poly_eff"), ("machine", "design_pr")]),
]

N_DESIGNS = 14
N_LOADED_DESIGNS = 6
LOADED_REFERENCES = {"RIG-CMP7B", "HPC-4X"}


def build(path: Path | str = db.DB_PATH, force: bool = False) -> Path:
    path = Path(path)
    if path.exists():
        if not force:
            return path
        path.unlink()
    conn = db.connect(path)
    conn.executescript(db.SCHEMA)
    conn.executemany("INSERT INTO components VALUES (?,?,?,?)", COMPONENTS)
    conn.executemany("INSERT INTO metrics VALUES (?,?,?,?,?,?,?)", METRICS)
    conn.executemany("INSERT INTO op_points VALUES (?,?)",
                     [(op, i) for i, op in enumerate(OP_POINTS)])

    comp_type = {c[0]: c[2] for c in COMPONENTS}

    # ---- design iterations -------------------------------------------------
    for i in range(N_DESIGNS):
        sid = f"DES-{i + 1:03d}"
        traits = DesignTraits(i, sid)
        loaded = i < N_LOADED_DESIGNS
        conn.execute(
            "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)",
            (sid, "design", sid, i, "CMP-8 3-stage front block",
             f"2026-{1 + i // 3:02d}-{4 + (i * 5) % 24:02d}", None,
             _design_note(i), int(loaded), i if loaded else None),
        )
        _write_source(conn, sid, traits, comps=[c[0] for c in COMPONENTS],
                      profile_ops=OP_POINTS, n_radial=21, noise=0.0,
                      comp_type=comp_type, scalars=None)

    # ---- reference data ----------------------------------------------------
    for j, ref in enumerate(REFERENCES):
        traits = DesignTraits(ref["traits_idx"], ref["source_id"])
        if ref["source_id"] == "HPC-4X":       # a different machine: shifted duty
            traits.eff_peak -= 1.15
            traits.pr_peak -= 0.34
            traits.flow_shift -= 1.6
        if ref["source_id"] == "RIG-CMP7B":    # test always reads below CFD
            traits.eff_peak -= 0.62
        loaded = ref["source_id"] in LOADED_REFERENCES
        conn.execute(
            "INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)",
            (ref["source_id"], "reference", ref["label"], j, ref["hardware"],
             ref["created"], ref["ref_type"], ref["notes"], int(loaded), None),
        )
        _write_source(conn, ref["source_id"], traits, comps=ref["comps"],
                      profile_ops=ref["profile_ops"], n_radial=ref["n_radial"],
                      noise=ref["noise"], comp_type=comp_type, scalars=ref["scalars"])

    conn.commit()
    conn.close()
    return path


def _design_note(i: int) -> str:
    notes = [
        "Baseline aero from the CMP-7B scale.",
        "R1 restagger +1.5 deg, tip clearance reduced to 0.30 mm.",
        "New S1 camber distribution, hub endwall contoured.",
        "R1 leading-edge recontour — forced response regression, do not build.",
        "Reverted R1 LE, kept the S1 endwall contour.",
        "R2/R3 restagger for surge margin.",
        "Tip clearance study, 0.25 mm.",
        "S2 3D stack, revised throat area.",
        "R1 thickness taper for flutter margin.",
        "Bleed port relocated downstream of S2.",
        "R3 aspect ratio reduction.",
        "Matched R1/R2 incidence at part speed.",
        "S3 exit angle retuned for the combustor.",
        "Release candidate — all margins closed.",
    ]
    return notes[i % len(notes)]


def _write_source(conn, sid, traits, comps, profile_ops, n_radial, noise, comp_type, scalars):
    r = np.linspace(0.02, 0.98, n_radial)
    scalar_filter = set(scalars) if scalars is not None else None

    for comp in comps:
        ctype = comp_type[comp]
        plots = PLOTS_BY_TYPE[ctype]

        for metric in plots["scalar"]:
            if scalar_filter is not None and (comp, metric) not in scalar_filter:
                continue
            val = scalar_value(metric, comp, ctype, traits)
            if noise:
                val = val * (1 + 0.004 * noise * RNG.normal())
            conn.execute("INSERT INTO scalars VALUES (?,?,?,?)", (sid, comp, metric, float(val)))

        flow = flow_grid(traits, 14 if noise < 0.5 else 11)
        for metric in plots["curve"]:
            y = curve_values(metric, comp, traits, flow, noise)
            conn.executemany(
                "INSERT INTO curve_points VALUES (?,?,?,?,?,?)",
                [(sid, comp, metric, 100.0, float(fx), float(fy)) for fx, fy in zip(flow, y)],
            )

        for metric in plots["profile"]:
            for op in profile_ops:
                vals = profile_values(metric, comp, ctype, traits, OP_FRAC[op], r)
                if noise:
                    vals = vals * (1 + 0.004 * noise * RNG.normal(0, 1, vals.shape))
                conn.executemany(
                    "INSERT INTO profile_points VALUES (?,?,?,?,?,?)",
                    [(sid, comp, metric, op, float(rr), float(vv)) for rr, vv in zip(r, vals)],
                )
