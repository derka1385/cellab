"""
celllab_physics.py — CellLab geometric physics core
====================================================

Answers one question per red blood cell (RBC):
    "Can this cell pass through a capillary / channel of diameter D, and at what cost?"

The model is GEOMETRIC, not mechanical. It rests on two well-established facts:
  1. The RBC membrane is almost inextensible in area: it lyses after roughly
     3-4 % area expansion (Evans, Waugh & Melnik 1976).
  2. Cell volume is ~constant during a fast transit.
So for a given surface area S and volume V, there is a minimum cylindrical diameter
(MCD) below which the cell cannot pass, however soft it is (Canham & Burton 1968).
Namvar et al. 2021 showed experimentally that the S/V ratio, not stiffness, is the
main determinant of RBC traversal through small channels.

Geometry used inside the channel: a cylinder of radius R closed by two hemispherical
caps (a "capsule"). With V and R fixed, the surface the cell NEEDS is

        V = R*S/2 - (2/3)*pi*R^3     <=>     S_required(D) = 4V/D + (pi/3)*D^2

and the MCD is the diameter where S_required(D) == S (smallest root, D < sphere diameter).

What this module does NOT do: it does not solve membrane mechanics, it does not
predict stiffness from an image. Stiffness is only ever an explicit user/agent
HYPOTHESIS, reported separately and never mixed into the geometric verdict.

Every number returned carries a provenance tag:
    MEASURED   : read directly from the image (pixels -> µm)
    CONSTRAINED: fixed by an external lab value (CBC: MCV, RDW, MCHC)
    INFERRED   : model output derived from the above (shape model, S, V per cell)
    COMPUTED   : deterministic physics on top of inferred values (MCD, verdict)
    HYPOTHESIS : value chosen by the user/agent to explore "what if"

Dependencies: numpy, scipy (matplotlib only for the demo plot).

Usage:
    python celllab_physics.py --selftest
    python celllab_physics.py --demo      # synthetic healthy vs spherocytosis, writes PNG + JSON
    python celllab_physics.py --mesh      # writes example STL + JSON meshes (healthy vs spherocyte)
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass, field, asdict
from typing import Callable, Dict, List, Optional, Sequence

import numpy as np
from scipy.optimize import brentq

# ---------------------------------------------------------------------------
# Constants (literature values, all in µm / µm² / µm³ = fL)
# ---------------------------------------------------------------------------

# Evans & Fung 1972 average discocyte: total thickness
#   T(x) = sqrt(1 - x^2) * (C0 + C2 x^2 + C4 x^4),  x = r / R0
EF_R0 = 3.91          # µm, cell radius
EF_C0 = 0.81          # µm
EF_C2 = 7.83          # µm
EF_C4 = -4.39         # µm

LYSIS_AREA_STRAIN = 0.03     # ~3 % area expansion before lysis (conservative)
SPHERICITY_K = (36 * math.pi) ** (1 / 3)   # 4.836 ; SI = K * V^(2/3) / S  (sphere = 1)

# Reference sphericity index values used to infer S from the image (INFERRED, tunable)
SI_DISCOCYTE = 0.74    # Evans-Fung normal cell (computed below in selftest ≈ 0.73-0.75)
SI_SPHEROCYTE = 0.92   # strongly spherical cell, no central pallor
PALLOR_RATIO_NORMAL = 0.40   # central pallor diameter / cell diameter for a normal cell


# ---------------------------------------------------------------------------
# Provenance-tagged value
# ---------------------------------------------------------------------------

@dataclass
class Tagged:
    value: float
    unit: str
    provenance: str          # MEASURED | CONSTRAINED | INFERRED | COMPUTED | HYPOTHESIS
    note: str = ""

    def to_dict(self) -> Dict:
        return {"value": round(float(self.value), 4), "unit": self.unit,
                "provenance": self.provenance, "note": self.note}


# ---------------------------------------------------------------------------
# 1. Core geometry: required surface, minimum cylindrical diameter, verdict
# ---------------------------------------------------------------------------

def sphere_diameter(V: float) -> float:
    """Diameter of the sphere of volume V (µm)."""
    return (6.0 * V / math.pi) ** (1 / 3)


def sphericity_index(V: float, S: float) -> float:
    """SI = K V^(2/3) / S. 1 for a sphere, ~0.73 for a normal discocyte."""
    return SPHERICITY_K * V ** (2 / 3) / S


def surface_required(D: float, V: float) -> float:
    """Surface a cell of volume V needs to fit as a capsule in a tube of diameter D."""
    return 4.0 * V / D + (math.pi / 3.0) * D ** 2


def min_cylindrical_diameter(V: float, S: float, area_strain: float = 0.0) -> float:
    """
    Minimum cylindrical diameter (µm) for a cell of volume V and surface S,
    allowing the membrane to expand by `area_strain` (0 = no stretch).
    Returns the sphere diameter if the cell is already a sphere (no reserve).
    """
    S_eff = S * (1.0 + area_strain)
    d_sph = sphere_diameter(V)
    # If the cell has less surface than a sphere of the same volume, it is unphysical.
    if S_eff <= surface_required(d_sph, V) + 1e-9:
        return d_sph
    f = lambda D: surface_required(D, V) - S_eff
    return brentq(f, 1e-3, d_sph)


def capsule_shape(V: float, D: float) -> Dict[str, float]:
    """
    Shape of the cell inside a tube of diameter D (for the 3D animation):
    cylinder of radius R = D/2 and length L, closed by hemispherical caps, volume V.
    L can be 0 if the tube is wider than the sphere of volume V (cell not confined).
    """
    R = D / 2.0
    L = max(0.0, (V - (4 / 3) * math.pi * R ** 3) / (math.pi * R ** 2))
    return {"radius_um": R, "cylinder_length_um": L, "total_length_um": L + 2 * R,
            "surface_um2": 2 * math.pi * R * L + 4 * math.pi * R ** 2}


@dataclass
class PassageResult:
    capillary_diameter_um: float
    mcd_um: float                     # MCD with no stretch
    mcd_at_lysis_um: float            # MCD if membrane stretched to lysis limit
    surface_reserve: float            # S / S_required - 1  (>0: spare membrane)
    area_strain_needed: float         # max(0, S_required / S - 1)
    verdict: str                      # PASSES | PASSES_UNDER_STRAIN | BLOCKED
    stiffness_hypothesis: Optional[float] = None
    caveat: str = ""

    def to_dict(self) -> Dict:
        d = asdict(self)
        d["provenance"] = "COMPUTED"
        return d


def passage(V: float, S: float, D_cap: float,
            lysis_strain: float = LYSIS_AREA_STRAIN,
            stiffness_hypothesis: Optional[float] = None) -> PassageResult:
    """
    Geometric verdict for one cell in a cylindrical channel of diameter D_cap.
      PASSES               : enough membrane, no stretching needed
      PASSES_UNDER_STRAIN  : needs 0 < strain <= lysis limit (high mechanical cost, lysis risk)
      BLOCKED              : would need more stretch than the membrane tolerates
    `stiffness_hypothesis` (x times normal) is only carried along: geometry is necessary,
    not sufficient. A rigid cell (e.g. sickle) may fail even with a PASSES verdict.
    """
    S_req = surface_required(D_cap, V)
    reserve = S / S_req - 1.0
    strain_needed = max(0.0, S_req / S - 1.0)
    if strain_needed == 0.0:
        verdict = "PASSES"
    elif strain_needed <= lysis_strain:
        verdict = "PASSES_UNDER_STRAIN"
    else:
        verdict = "BLOCKED"
    caveat = ""
    if stiffness_hypothesis is not None and stiffness_hypothesis > 1.0 and verdict != "BLOCKED":
        caveat = (f"Geometric verdict only. Under the hypothesis of {stiffness_hypothesis:g}x "
                  "normal stiffness, transit would be slower/harder; this is NOT quantified "
                  "by this model and must be tested experimentally.")
    return PassageResult(
        capillary_diameter_um=D_cap,
        mcd_um=min_cylindrical_diameter(V, S),
        mcd_at_lysis_um=min_cylindrical_diameter(V, S, lysis_strain),
        surface_reserve=reserve,
        area_strain_needed=strain_needed,
        verdict=verdict,
        stiffness_hypothesis=stiffness_hypothesis,
        caveat=caveat,
    )


# ---------------------------------------------------------------------------
# 2. From image measurements + CBC to per-cell V and S (INFERRED)
# ---------------------------------------------------------------------------

@dataclass
class CellMeasurement:
    """What the vision module must produce for each cell (all MEASURED)."""
    cell_id: str
    area_um2: float               # projected area
    diameter_um: float            # equivalent or Feret diameter
    circularity: float            # 4*pi*A / P^2
    pallor_ratio: float           # central pallor diameter / cell diameter (0 = none)
    shape_class: str = "unknown"  # optional classifier output (normal, spherocyte, sickle, ...)


@dataclass
class CBC:
    """Complete blood count values (CONSTRAINED)."""
    mcv_fl: float                   # mean corpuscular volume
    rdw_cv_pct: Optional[float] = None
    mchc_g_dl: Optional[float] = None


def si_from_pallor(pallor_ratio: float,
                   si_disc: float = SI_DISCOCYTE,
                   si_sphere: float = SI_SPHEROCYTE,
                   p_norm: float = PALLOR_RATIO_NORMAL) -> float:
    """
    INFERRED sphericity from central pallor: a cell that has lost its central pallor is
    more spherical. Linear interpolation, clipped. This is the main modelling assumption
    of the pipeline and is shown as such in the UI.
    """
    w = min(max(pallor_ratio / p_norm, 0.0), 1.0)
    return si_sphere - (si_sphere - si_disc) * w


def infer_population(cells: Sequence[CellMeasurement], cbc: CBC) -> List[Dict]:
    """
    Per-cell V and S.
      V_i = MCV * (A_i / median(A))^(3/2)    -> mean volume is anchored on the CBC
      SI_i from pallor                        -> S_i = K V_i^(2/3) / SI_i
    Smear drying distorts absolute diameters, so the image only provides RELATIVE size
    and shape; the CBC provides the absolute scale.
    """
    areas = np.array([c.area_um2 for c in cells], dtype=float)
    a_med = float(np.median(areas))
    raw = (areas / a_med) ** 1.5
    scale = cbc.mcv_fl / float(np.mean(raw))     # exact match of population mean to MCV
    out = []
    for c, r in zip(cells, raw):
        V = scale * r
        SI = si_from_pallor(c.pallor_ratio)
        S = SPHERICITY_K * V ** (2 / 3) / SI
        out.append({
            "cell_id": c.cell_id,
            "shape_class": c.shape_class,
            "measured": {
                "area_um2": Tagged(c.area_um2, "µm²", "MEASURED").to_dict(),
                "diameter_um": Tagged(c.diameter_um, "µm", "MEASURED").to_dict(),
                "circularity": Tagged(c.circularity, "", "MEASURED").to_dict(),
                "pallor_ratio": Tagged(c.pallor_ratio, "", "MEASURED").to_dict(),
            },
            "volume_fl": Tagged(V, "fL", "INFERRED",
                                "relative size from image, absolute scale from CBC MCV").to_dict(),
            "sphericity_index": Tagged(SI, "", "INFERRED", "from central pallor").to_dict(),
            "surface_um2": Tagged(S, "µm²", "INFERRED", "S = K V^(2/3) / SI").to_dict(),
            "mcd_um": Tagged(min_cylindrical_diameter(V, S), "µm", "COMPUTED",
                             "capsule model, no membrane stretch").to_dict(),
        })
    return out


def cbc_consistency(cells: Sequence[CellMeasurement], cbc: CBC) -> List[Dict]:
    """
    Cross-checks the agent should run and report (each one is a flag, not a diagnosis).
    1. RDW vs image: V ∝ D^3  =>  CV(V) ≈ 3 CV(D). Compares RDW-CV with 3x diameter CV.
    2. MCHC vs pallor: high MCHC (> 36 g/dL) + many cells without pallor is a coherent pattern
       (dense, spherical cells); high MCHC with normal pallor everywhere is incoherent.
    """
    flags = []
    d = np.array([c.diameter_um for c in cells])
    cv_d = float(np.std(d) / np.mean(d) * 100)
    if cbc.rdw_cv_pct is not None:
        implied = 3 * cv_d
        ratio = implied / cbc.rdw_cv_pct
        status = "COHERENT" if 0.6 <= ratio <= 1.6 else "INCOHERENT"
        flags.append({"check": "RDW_vs_diameter_CV", "status": status,
                      "rdw_cv_pct": cbc.rdw_cv_pct, "image_diameter_cv_pct": round(cv_d, 2),
                      "implied_rdw_from_image_pct": round(implied, 2),
                      "note": "Approximation V∝D³; smear artefacts widen the image CV."})
    if cbc.mchc_g_dl is not None:
        frac_no_pallor = float(np.mean([c.pallor_ratio < 0.1 for c in cells]))
        high_mchc = cbc.mchc_g_dl > 36.0
        if high_mchc and frac_no_pallor >= 0.05:
            status = "COHERENT"
        elif high_mchc and frac_no_pallor < 0.05:
            status = "INCOHERENT"
        elif (not high_mchc) and frac_no_pallor >= 0.2:
            status = "INCOHERENT"
        else:
            status = "COHERENT"
        flags.append({"check": "MCHC_vs_pallor", "status": status,
                      "mchc_g_dl": cbc.mchc_g_dl,
                      "fraction_cells_without_pallor": round(frac_no_pallor, 3)})
    return flags


# ---------------------------------------------------------------------------
# 3. Population sweep (the key scientific chart)
# ---------------------------------------------------------------------------

def sweep_capillary(V: np.ndarray, S: np.ndarray,
                    diameters: np.ndarray = np.linspace(2.0, 5.0, 61),
                    lysis_strain: float = LYSIS_AREA_STRAIN) -> Dict:
    """
    For each channel diameter: fraction of cells that PASS, PASS_UNDER_STRAIN, are BLOCKED.
    Vectorised: S_req = 4V/D + pi D^2 / 3.
    """
    V = np.asarray(V, float)[None, :]
    S = np.asarray(S, float)[None, :]
    D = np.asarray(diameters, float)[:, None]
    S_req = 4 * V / D + (np.pi / 3) * D ** 2
    strain = S_req / S - 1
    passes = (strain <= 0).mean(axis=1)
    strained = ((strain > 0) & (strain <= lysis_strain)).mean(axis=1)
    blocked = (strain > lysis_strain).mean(axis=1)
    return {"diameters_um": diameters.tolist(), "passes": passes.tolist(),
            "passes_under_strain": strained.tolist(), "blocked": blocked.tolist(),
            "provenance": "COMPUTED"}


def d50(sweep: Dict) -> float:
    """Diameter at which 50 % of cells pass without strain (interpolated)."""
    D = np.array(sweep["diameters_um"])
    p = np.array(sweep["passes"])
    if p.max() < 0.5:
        return float("nan")
    return float(np.interp(0.5, p, D))


def design_experiment(sweep_a: Dict, sweep_b: Dict, label_a: str = "A", label_b: str = "B",
                      alpha: float = 0.05, power: float = 0.80) -> Dict:
    """
    Turn two simulated passage curves into a testable microfluidic experiment:
      - the channel width where the two samples differ most (max |pA - pB|),
      - two flanking widths (±0.25 µm) to see the curve, not one point,
      - predicted pass fractions (the hypothesis to falsify),
      - cells to count per sample for a two-proportion z-test.
    All numbers are COMPUTED from the geometric model; they are predictions, not results.
    """
    from scipy.stats import norm
    D = np.array(sweep_a["diameters_um"])
    pa, pb = np.array(sweep_a["passes"]), np.array(sweep_b["passes"])
    i = int(np.argmax(np.abs(pa - pb)))
    d_star = round(float(D[i]), 2)
    p1 = round(float(np.interp(d_star, D, pa)), 3)
    p2 = round(float(np.interp(d_star, D, pb)), 3)
    za, zb = norm.ppf(1 - alpha / 2), norm.ppf(power)
    pbar = (p1 + p2) / 2
    diff = abs(p1 - p2)
    if diff < 1e-6:
        n = None
    else:
        n = ((za * math.sqrt(2 * pbar * (1 - pbar)) + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2)))
             / diff) ** 2
        n = int(math.ceil(n))
    widths = [round(d_star - 0.25, 2), round(d_star, 2), round(d_star + 0.25, 2)]
    preds = {w: {label_a: round(float(np.interp(w, D, pa)), 3),
                 label_b: round(float(np.interp(w, D, pb)), 3)} for w in widths}
    return {
        "most_discriminating_width_um": d_star,
        "suggested_constriction_widths_um": widths,
        "predicted_pass_fraction": preds,
        "cells_per_sample_for_power": n,
        "statistics": f"two-proportion z-test, alpha={alpha}, power={power}",
        "hypothesis": (f"At {d_star:.2f} µm, {label_a} passes at {p1:.0%} vs {label_b} at "
                       f"{p2:.0%}, driven by surface-to-volume ratio alone."),
        "falsified_if": ("Measured pass fractions do not differ, or the difference disappears "
                         "after osmotic swelling/shrinking controls."),
        "caveats": ["Model assumes cylindrical channels; rectangular microfluidic channels "
                    "need an equivalent-diameter correction.",
                    "Stiffness is not modelled; rigid cells may fail where geometry allows passage."],
        "provenance": "COMPUTED",
    }


# ---------------------------------------------------------------------------
# 4. 3D shape: Evans-Fung discocyte morphed towards a sphere, matched to (V, S)
# ---------------------------------------------------------------------------

def ef_half_thickness(x: np.ndarray) -> np.ndarray:
    """Evans-Fung half thickness for R0 = 3.91 µm (µm), x = r/R0 in [0,1]."""
    x = np.clip(x, 0, 1)
    return 0.5 * np.sqrt(1 - x ** 2) * (EF_C0 + EF_C2 * x ** 2 + EF_C4 * x ** 4)


MORPH_T_MIN = -0.6   # t < 0: flatter-than-average discocyte (thickness x (1+t))


def morphed_profile(t: float, R: float = EF_R0) -> Callable[[np.ndarray], np.ndarray]:
    """
    Half thickness h(r) for morph t in [MORPH_T_MIN, 1]:
      t = 0  -> Evans-Fung average discocyte
      t = 1  -> sphere of radius R
      t < 0  -> flatter discocyte (more surface reserve, lower sphericity)
    """
    s = R / EF_R0
    def h(r):
        x = np.clip(r / R, 0, 1)
        if t < 0:
            return (1 + t) * s * ef_half_thickness(x)
        return (1 - t) * s * ef_half_thickness(x) + t * R * np.sqrt(1 - x ** 2)
    return h


def axisym_volume_surface(h: Callable, R: float, n: int = 4000) -> (float, float):
    """Volume and surface of the closed axisymmetric body z = ±h(r), 0<=r<=R."""
    # Parameterise by angle to handle the vertical tangent at the rim smoothly.
    th = np.linspace(0, math.pi / 2, n)
    r = R * np.sin(th)
    z = h(r)
    V = 2 * np.trapezoid(2 * math.pi * r * z, r)
    dr = np.diff(r)
    dz = np.diff(z)
    rm = 0.5 * (r[1:] + r[:-1])
    S = 2 * np.sum(2 * math.pi * rm * np.sqrt(dr ** 2 + dz ** 2))
    return float(V), float(S)


def shape_for(V: float, S: float) -> Dict:
    """
    Find morph t so that the shape's sphericity index matches SI(V,S), then scale it to
    volume V. Returns parameters for the mesh generator. SI outside the family is clipped.
    """
    target = sphericity_index(V, S)
    def si_of(t):
        v, s = axisym_volume_surface(morphed_profile(t), EF_R0)
        return sphericity_index(v, s)
    si0, si1 = si_of(MORPH_T_MIN), si_of(1.0)
    if target <= si0:
        t = MORPH_T_MIN
    elif target >= si1:
        t = 1.0
    else:
        t = brentq(lambda tt: si_of(tt) - target, MORPH_T_MIN, 1.0, xtol=1e-4)
    v_unit, _ = axisym_volume_surface(morphed_profile(t), EF_R0)
    R = EF_R0 * (V / v_unit) ** (1 / 3)
    v_chk, s_chk = axisym_volume_surface(morphed_profile(t, R), R)
    return {"morph_t": t, "radius_um": R, "volume_fl": v_chk, "surface_um2": s_chk,
            "target_si": target, "achieved_si": sphericity_index(v_chk, s_chk),
            "provenance": "INFERRED"}


def mesh_cell(morph_t: float, R: float, n_theta: int = 48, n_phi: int = 64) -> Dict:
    """Triangle mesh (vertices, faces) of the axisymmetric cell. Y axis = thickness."""
    h = morphed_profile(morph_t, R)
    th = np.linspace(0, math.pi, n_theta + 1)            # 0 = top pole, pi = bottom pole
    phis = np.linspace(0, 2 * math.pi, n_phi, endpoint=False)
    verts = []
    for t in th:
        r = R * math.sin(t)
        zz = float(h(np.array([r]))[0]) * (1 if t <= math.pi / 2 else -1)
        if t in (0.0, math.pi):
            verts.append([0.0, zz, 0.0])
            continue
        for p in phis:
            verts.append([r * math.cos(p), zz, r * math.sin(p)])
    faces = []
    # top cap
    for j in range(n_phi):
        faces.append([0, 1 + (j + 1) % n_phi, 1 + j])
    # rings
    rings = n_theta - 1
    for i in range(rings - 1):
        a0 = 1 + i * n_phi
        b0 = 1 + (i + 1) * n_phi
        for j in range(n_phi):
            a, a2 = a0 + j, a0 + (j + 1) % n_phi
            b, b2 = b0 + j, b0 + (j + 1) % n_phi
            faces.append([a, a2, b2])
            faces.append([a, b2, b])
    bottom = len(verts) - 1
    last = 1 + (rings - 1) * n_phi
    for j in range(n_phi):
        faces.append([bottom, last + j, last + (j + 1) % n_phi])
    return {"vertices": verts, "faces": faces, "units": "µm"}


def write_stl(mesh: Dict, path: str, scale: float = 1.0, name: str = "cell") -> None:
    """
    ASCII STL. Mesh vertices are in µm; slicers read STL units as mm.
    scale=1 -> an 8 µm cell becomes an 8 mm object (x1000). scale=5 -> 40 mm (x5000).
    """
    v = np.array(mesh["vertices"]) * scale
    with open(path, "w") as f:
        f.write(f"solid {name}\n")
        for a, b, c in mesh["faces"]:
            p0, p1, p2 = v[a], v[b], v[c]
            n = np.cross(p1 - p0, p2 - p0)
            ln = np.linalg.norm(n)
            n = n / ln if ln > 0 else n
            f.write(f"facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n outer loop\n")
            for p in (p0, p1, p2):
                f.write(f"  vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}\n")
            f.write(" endloop\nendfacet\n")
        f.write(f"endsolid {name}\n")


# ---------------------------------------------------------------------------
# 5. Synthetic populations (until real images are processed)
# ---------------------------------------------------------------------------

def synthetic_population(kind: str, n: int = 2000, seed: int = 0) -> Dict[str, np.ndarray]:
    """
    Plausible demo populations. NOT patient data — label them 'synthetic' in the UI.
      healthy      : V ~ N(90, 8) fL, SI ~ N(0.74, 0.025)
      spherocytosis: 70 % near-normal cells + 30 % spherocytes (SI ~ N(0.88, 0.03), V ~ N(80, 8))
    """
    rng = np.random.default_rng(seed)
    if kind == "healthy":
        V = rng.normal(90, 8, n)
        SI = rng.normal(0.74, 0.025, n)
    elif kind == "spherocytosis":
        k = int(0.3 * n)
        V = np.concatenate([rng.normal(88, 8, n - k), rng.normal(80, 8, k)])
        SI = np.concatenate([rng.normal(0.77, 0.03, n - k), rng.normal(0.88, 0.03, k)])
    else:
        raise ValueError(kind)
    V = np.clip(V, 50, 140)
    SI = np.clip(SI, 0.62, 0.99)
    S = SPHERICITY_K * V ** (2 / 3) / SI
    return {"V": V, "S": S, "SI": SI}


# ---------------------------------------------------------------------------
# 6. Self-tests (run these before trusting anything)
# ---------------------------------------------------------------------------

def selftest() -> None:
    ok = True
    def check(name, cond, info=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'OK' if cond else 'FAIL'}] {name} {info}")

    V, S = axisym_volume_surface(lambda r: ef_half_thickness(r / EF_R0), EF_R0)
    check("Evans-Fung volume ~ 94 fL", 85 < V < 100, f"(V={V:.1f})")
    check("Evans-Fung surface ~ 135 µm²", 125 < S < 145, f"(S={S:.1f})")
    si = sphericity_index(V, S)
    check("Evans-Fung sphericity ~ 0.73-0.75", 0.70 < si < 0.78, f"(SI={si:.3f})")

    mcd = min_cylindrical_diameter(V, S)
    check("MCD of normal cell ~ 2.7-3.1 µm (Canham-Burton / Namvar)", 2.6 < mcd < 3.2,
          f"(MCD={mcd:.2f} µm)")
    mcd2 = min_cylindrical_diameter(99, 149)
    check("MCD for Namvar 2021 mean cell (V=99, S=149) ~ 2.8-3.1", 2.7 < mcd2 < 3.15,
          f"(MCD={mcd2:.2f} µm)")

    Vs = 90.0
    Ssph = math.pi * sphere_diameter(Vs) ** 2
    check("Sphere: MCD == sphere diameter", abs(min_cylindrical_diameter(Vs, Ssph)
                                                  - sphere_diameter(Vs)) < 1e-6)

    # consistency: at D = MCD, required surface equals S
    check("S_required(MCD) == S", abs(surface_required(mcd, V) - S) < 1e-6)
    # capsule at MCD has surface S
    cap = capsule_shape(V, mcd)
    check("Capsule at MCD has surface S", abs(cap["surface_um2"] - S) < 1e-6)

    # monotonicity: lower S/V -> higher MCD
    check("Less surface -> larger MCD", min_cylindrical_diameter(90, 120) >
          min_cylindrical_diameter(90, 135))

    # verdict boundaries
    r_big = passage(V, S, 5.0)
    r_small = passage(V, S, 2.0)
    check("Wide channel PASSES", r_big.verdict == "PASSES")
    check("2 µm channel BLOCKED", r_small.verdict == "BLOCKED")
    r_edge = passage(V, S, mcd * 0.99)
    check("Just below MCD -> PASSES_UNDER_STRAIN", r_edge.verdict == "PASSES_UNDER_STRAIN")

    # shape matching
    sh = shape_for(90, 135)
    check("shape_for matches volume", abs(sh["volume_fl"] - 90) < 0.5, f"({sh['volume_fl']:.2f})")
    check("shape_for matches sphericity", abs(sh["achieved_si"] - sh["target_si"]) < 0.01,
          f"(t={sh['morph_t']:.3f})")
    sh2 = shape_for(80, SPHERICITY_K * 80 ** (2 / 3) / 0.9)
    check("spherocyte morph t > discocyte", sh2["morph_t"] > sh["morph_t"],
          f"(t={sh2['morph_t']:.3f})")

    # mesh closed: Euler characteristic V - E + F = 2
    m = mesh_cell(sh["morph_t"], sh["radius_um"], 24, 32)
    nv, nf = len(m["vertices"]), len(m["faces"])
    edges = set()
    for a, b, c in m["faces"]:
        for e in ((a, b), (b, c), (c, a)):
            edges.add(tuple(sorted(e)))
    check("Mesh is closed (Euler = 2)", nv - len(edges) + nf == 2)

    # inference pipeline: mean V equals MCV
    rng = np.random.default_rng(1)
    cells = [CellMeasurement(f"c{i}", a, 2 * math.sqrt(a / math.pi), 0.9, p)
             for i, (a, p) in enumerate(zip(rng.normal(45, 4, 100), rng.uniform(0, 0.45, 100)))]
    pop = infer_population(cells, CBC(mcv_fl=88))
    meanV = np.mean([c["volume_fl"]["value"] for c in pop])
    check("Population mean V anchored on MCV", abs(meanV - 88) < 0.01, f"({meanV:.3f})")

    # sweep: healthy D50 < spherocytosis D50
    h = synthetic_population("healthy")
    s = synthetic_population("spherocytosis")
    dh = d50(sweep_capillary(h["V"], h["S"]))
    ds = d50(sweep_capillary(s["V"], s["S"]))
    check("D50 healthy < D50 spherocytosis", dh < ds, f"(healthy {dh:.2f} µm, HS {ds:.2f} µm)")
    ex = design_experiment(sweep_capillary(h["V"], h["S"]), sweep_capillary(s["V"], s["S"]))
    check("Experiment width between the two D50s", dh - 0.3 <= ex["most_discriminating_width_um"]
          <= ds + 0.3, f"({ex['most_discriminating_width_um']} µm, "
          f"n={ex['cells_per_sample_for_power']} cells/sample)")

    print("\nALL TESTS PASSED" if ok else "\nSOME TESTS FAILED")
    if not ok:
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# 7. Demo outputs
# ---------------------------------------------------------------------------

def demo(outdir: str = ".") -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    D = np.linspace(2.0, 5.0, 121)
    h = synthetic_population("healthy", seed=1)
    s = synthetic_population("spherocytosis", seed=2)
    sh = sweep_capillary(h["V"], h["S"], D)
    ss = sweep_capillary(s["V"], s["S"], D)

    fig, ax = plt.subplots(figsize=(8, 4.8), dpi=150)
    ax.plot(D, np.array(sh["passes"]) * 100, lw=2.4, color="#2a6f97", label="Healthy (synthetic)")
    ax.plot(D, np.array(ss["passes"]) * 100, lw=2.4, color="#c0392b",
            label="Spherocytosis-like (synthetic)")
    ax.plot(D, (np.array(sh["passes"]) + np.array(sh["passes_under_strain"])) * 100, lw=1.2,
            ls="--", color="#2a6f97", alpha=0.7, label="Healthy, incl. ≤3 % membrane stretch")
    ax.plot(D, (np.array(ss["passes"]) + np.array(ss["passes_under_strain"])) * 100, lw=1.2,
            ls="--", color="#c0392b", alpha=0.7, label="Spherocytosis, incl. ≤3 % stretch")
    ax.set_xlabel("Channel diameter (µm)")
    ax.set_ylabel("Cells passing (%)")
    ax.set_title("CellLab — geometric passage curve (S/V model, Canham–Burton capsule)")
    ax.set_ylim(0, 102)
    ax.grid(alpha=0.25)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    png = f"{outdir}/passage_curve_demo.png"
    fig.savefig(png)

    summary = {
        "healthy": {"D50_um": round(d50(sh), 3),
                    "median_MCD_um": round(float(np.median(
                        [min_cylindrical_diameter(v, a) for v, a in zip(h["V"], h["S"])])), 3)},
        "spherocytosis": {"D50_um": round(d50(ss), 3),
                          "median_MCD_um": round(float(np.median(
                              [min_cylindrical_diameter(v, a) for v, a in zip(s["V"], s["S"])])), 3)},
        "note": "Synthetic populations for demo purposes only. Not patient data.",
        "example_single_cell": passage(90, 135, 2.8).to_dict(),
        "experiment_proposal": design_experiment(sh, ss, "healthy", "spherocytosis"),
    }
    with open(f"{outdir}/passage_demo_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    print(json.dumps(summary, indent=2))
    print(f"wrote {png}")


def write_example_meshes(outdir: str = ".") -> None:
    for name, V, SI in (("healthy_discocyte", 90, 0.74), ("spherocyte", 80, 0.90)):
        S = SPHERICITY_K * V ** (2 / 3) / SI
        sh = shape_for(V, S)
        m = mesh_cell(sh["morph_t"], sh["radius_um"])
        write_stl(m, f"{outdir}/{name}_x5000.stl", scale=5.0, name=name)   # ~40 mm print
        with open(f"{outdir}/{name}_mesh.json", "w") as f:
            json.dump({**m, "shape": sh, "V": V, "S": S}, f)
        print(f"{name}: V={V} S={S:.1f} t={sh['morph_t']:.3f} R={sh['radius_um']:.2f} "
              f"MCD={min_cylindrical_diameter(V, S):.2f} µm")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--mesh", action="store_true")
    ap.add_argument("--out", default=".")
    a = ap.parse_args()
    if not (a.selftest or a.demo or a.mesh):
        a.selftest = True
    if a.selftest:
        selftest()
    if a.demo:
        demo(a.out)
    if a.mesh:
        write_example_meshes(a.out)
