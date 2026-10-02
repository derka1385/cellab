"""
CellLab agent tools (contract section 5).

Every tool is deterministic and returns a compact JSON summary (quantiles, fractions,
a handful of ids), never the raw per-cell arrays, so the LLM context stays small
(< 1500 characters per result, enforced by tests/test_agent.py).

The tools read population.json through backend.pipeline.build_population (cached on disk)
and call the physics core for anything that is recomputed (sweeps, single-cell passage,
experiment design).

`submit_report` is special: it needs every tool result of the run, so it is executed
through a RunContext (see `ToolRunner`) and calls backend.agent.number_guard.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from backend import pipeline
from backend.physics.celllab_physics import (
    LYSIS_AREA_STRAIN,
    PALLOR_RATIO_NORMAL,
    SI_DISCOCYTE,
    SI_SPHEROCYTE,
    capsule_shape,
    d50,
    design_experiment as physics_design_experiment,
    passage,
    sweep_capillary,
)

MAX_RESULT_CHARS = 1500
REFERENCE_WIDTHS_UM = [2.5, 3.0, 3.5, 4.0]
DISPLAY_REFERENCE_UM = 3.0


class ToolError(Exception):
    """Raised for bad tool input; returned to the agent as an is_error tool_result."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _r(x: Any, sig: int = 3) -> Any:
    """Round to `sig` significant figures (keeps results short and human-readable)."""
    if isinstance(x, (np.floating, np.integer)):
        x = x.item()
    if isinstance(x, bool) or x is None or isinstance(x, int):
        return x
    if isinstance(x, float):
        if math.isnan(x) or math.isinf(x):
            return None
        if x == 0:
            return 0.0
        return round(x, max(0, sig - 1 - int(math.floor(math.log10(abs(x))))))
    if isinstance(x, dict):
        return {k: _r(v, sig) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v, sig) for v in x]
    return x


def _quantiles(a: np.ndarray, sig: int = 3) -> Dict[str, float]:
    a = np.asarray(a, float)
    return {"p10": _r(float(np.percentile(a, 10)), sig),
            "p50": _r(float(np.percentile(a, 50)), sig),
            "p90": _r(float(np.percentile(a, 90)), sig)}


def _sample_ids() -> List[str]:
    return pipeline.list_samples()


def _check_sample(sample_id: Any) -> str:
    if not isinstance(sample_id, str) or sample_id not in _sample_ids():
        raise ToolError(f"unknown sample_id {sample_id!r}; available: {_sample_ids()}")
    return sample_id


def _read_json(path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass
class _Pop:
    sample_id: str
    ids: List[str]
    shape_class: List[str]
    V: np.ndarray
    S: np.ndarray
    SI: np.ndarray
    MCD: np.ndarray
    pallor: np.ndarray
    diameter: np.ndarray
    raw: Dict = field(repr=False, default_factory=dict)


_POP_CACHE: Dict[str, tuple] = {}


def load_population(sample_id: str) -> _Pop:
    """Population arrays for one sample (cached in memory, keyed on population.json mtime)."""
    sample_id = _check_sample(sample_id)
    pop = pipeline.build_population(sample_id)
    p = pipeline.sample_dir(sample_id) / "population.json"
    key = p.stat().st_mtime if p.exists() else None
    hit = _POP_CACHE.get(sample_id)
    if hit and hit[0] == key and key is not None:
        return hit[1]
    cells = pop["cells"]
    out = _Pop(
        sample_id=sample_id,
        ids=[c["cell_id"] for c in cells],
        shape_class=[c.get("shape_class") or "unknown" for c in cells],
        V=np.array([c["volume_fl"]["value"] for c in cells], float),
        S=np.array([c["surface_um2"]["value"] for c in cells], float),
        SI=np.array([c["sphericity_index"]["value"] for c in cells], float),
        MCD=np.array([c["mcd_um"]["value"] for c in cells], float),
        pallor=np.array([c["measured"]["pallor_ratio"]["value"] for c in cells], float),
        diameter=np.array([c["measured"]["diameter_um"]["value"] for c in cells], float),
        raw=pop,
    )
    _POP_CACHE[sample_id] = (key, out)
    return out


def _full_sweep(p: _Pop) -> Dict:
    sw = p.raw.get("sweep")
    if sw and sw.get("diameters_um"):
        return sw
    return sweep_capillary(p.V, p.S, diameters=pipeline.SWEEP_DIAMETERS)


def _fractions_at(p: _Pop, widths: List[float]) -> Dict[str, Dict[str, float]]:
    sw = sweep_capillary(p.V, p.S, diameters=np.array(widths, float))
    return {f"{w:g}": {"passes": _r(sw["passes"][i]),
                       "under_strain": _r(sw["passes_under_strain"][i]),
                       "blocked": _r(sw["blocked"][i])}
            for i, w in enumerate(widths)}


# ---------------------------------------------------------------------------
# 1. list_samples
# ---------------------------------------------------------------------------

def list_samples() -> Dict:
    out = []
    for sid in _sample_ids():
        d = pipeline.sample_dir(sid)
        try:
            s = _read_json(d / "sample.json")
        except Exception:  # noqa: BLE001 - a broken sample must not break the agent
            continue
        cells = s.get("cells", [])
        out.append({
            "sample_id": sid,
            "label": (s.get("label") or "")[:80],
            "source": s.get("source"),
            "has_cbc": (d / "cbc.json").exists(),
            "n_cells": len(cells),
            "n_excluded": sum(1 for c in cells if c.get("excluded")),
            "has_image": bool(s.get("image_path")),
        })
    return {"samples": out[:12], "n_samples": len(out)}


# ---------------------------------------------------------------------------
# 2. measure_sample  (MEASURED)
# ---------------------------------------------------------------------------

def measure_sample(sample_id: str) -> Dict:
    sample_id = _check_sample(sample_id)
    s = _read_json(pipeline.sample_dir(sample_id) / "sample.json")
    cells = s.get("cells", [])
    kept = [c for c in cells if not c.get("excluded")]
    excl = Counter((c.get("exclusion_reason") or "unspecified") for c in cells if c.get("excluded"))
    if not kept:
        raise ToolError(f"{sample_id}: no non-excluded cells")
    diam = np.array([float(c["diameter"]) for c in kept])
    pallor = np.array([float(c["pallor_ratio"]) for c in kept])
    circ = np.array([float(c["circularity"]) for c in kept])
    unit = "µm" if s.get("pixel_size_um") else "px"
    classes = Counter((c.get("shape_class") or "unknown") for c in kept)
    sources = Counter((c.get("shape_class_source") or "none") for c in kept)
    return {
        "sample_id": sample_id,
        "source": s.get("source"),
        "provenance": "MEASURED",
        "n_kept": len(kept),
        "n_excluded": len(cells) - len(kept),
        "exclusion_reasons": dict(excl.most_common(4)),
        "diameter": {**_quantiles(diam), "unit": unit,
                     "cv_pct": _r(float(np.std(diam) / np.mean(diam) * 100))},
        "pallor_ratio": {**_quantiles(pallor),
                         "fraction_below_0.1": _r(float(np.mean(pallor < 0.1))),
                         "fraction_below_0.2": _r(float(np.mean(pallor < 0.2)))},
        "circularity_p50": _r(float(np.median(circ))),
        "shape_classes": dict(classes.most_common(6)),
        "shape_class_source": dict(sources),
        "note": ("Diameters in pixels; only ratios are used (the CBC fixes the absolute scale)."
                 if unit == "px" else ""),
    }


# ---------------------------------------------------------------------------
# 3. infer_geometry  (INFERRED + COMPUTED)
# ---------------------------------------------------------------------------

def infer_geometry(sample_id: str, si_threshold: Optional[float] = None) -> Dict:
    p = load_population(sample_id)
    cbc = _read_json(pipeline.sample_dir(p.sample_id) / "cbc.json")
    thresholds = sorted({0.8, 0.85, 0.9} | ({float(si_threshold)} if si_threshold else set()))
    return {
        "sample_id": p.sample_id,
        "n_cells": len(p.ids),
        "volume_fl": {**_quantiles(p.V), "mean": _r(float(p.V.mean())), "provenance": "INFERRED",
                      "constrained_by_mcv_fl": cbc.get("mcv_fl")},
        "surface_um2": {**_quantiles(p.S), "provenance": "INFERRED"},
        "sphericity_index": {**_quantiles(p.SI), "max": _r(float(p.SI.max())),
                             "provenance": "INFERRED", "note": "from central pallor"},
        "mcd_um": {**_quantiles(p.MCD), "max": _r(float(p.MCD.max())), "provenance": "COMPUTED"},
        "fraction_si_above": {f"{t:g}": _r(float(np.mean(p.SI > t))) for t in thresholds},
        "model_constants": {"si_discocyte": SI_DISCOCYTE, "si_spherocyte": SI_SPHEROCYTE,
                            "pallor_ratio_normal": PALLOR_RATIO_NORMAL,
                            "lysis_area_strain": LYSIS_AREA_STRAIN},
    }


# ---------------------------------------------------------------------------
# 4. check_cbc_consistency
# ---------------------------------------------------------------------------

def check_cbc_consistency(sample_id: str) -> Dict:
    p = load_population(sample_id)
    cbc = _read_json(pipeline.sample_dir(p.sample_id) / "cbc.json")
    checks = [{k: v for k, v in c.items()} for c in p.raw.get("consistency", [])]
    statuses = [c.get("status") for c in checks]
    return {
        "sample_id": p.sample_id,
        "cbc": {"mcv_fl": cbc.get("mcv_fl"), "rdw_cv_pct": cbc.get("rdw_cv_pct"),
                "mchc_g_dl": cbc.get("mchc_g_dl"), "source": cbc.get("source"),
                "provenance": "CONSTRAINED"},
        "checks": checks,
        "overall": "INCOHERENT" if "INCOHERENT" in statuses else "COHERENT",
        "note": "Flags, not diagnoses.",
    }


# ---------------------------------------------------------------------------
# 5. sweep_channels  (COMPUTED)
# ---------------------------------------------------------------------------

def sweep_channels(sample_ids: List[str], d_min: float = 2.0, d_max: float = 5.0) -> Dict:
    if not isinstance(sample_ids, list) or not sample_ids:
        raise ToolError("sample_ids must be a non-empty list")
    if len(sample_ids) > 3:
        raise ToolError("at most 3 samples per sweep")
    d_min, d_max = float(d_min), float(d_max)
    if not (1.5 <= d_min < d_max <= 8.0):
        raise ToolError("need 1.5 <= d_min < d_max <= 8.0 (µm)")
    # 7 evenly spaced widths inside the requested window (rounded to 0.05 µm)
    grid = sorted({round(round(x / 0.05) * 0.05, 2) for x in np.linspace(d_min, d_max, 7)})
    pops = [load_population(s) for s in sample_ids]
    per = {}
    for p in pops:
        full = _full_sweep(p)
        dv = d50(full)
        per[p.sample_id] = {
            "d50_um": _r(dv) if not math.isnan(dv) else None,
            "at_reference_widths": {k: v["passes"] for k, v in
                                    _fractions_at(p, REFERENCE_WIDTHS_UM).items()},
            "in_window": _fractions_at(p, grid),
        }
    out: Dict[str, Any] = {"window_um": [d_min, d_max], "provenance": "COMPUTED",
                           "per_sample": per,
                           "legend": "fractions of cells; passes = no membrane stretch needed"}
    if len(pops) >= 2:
        a, b = pops[0], pops[1]
        fine = np.round(np.arange(d_min, d_max + 1e-9, 0.025), 3)
        sa = sweep_capillary(a.V, a.S, diameters=fine)
        sb = sweep_capillary(b.V, b.S, diameters=fine)
        gap = np.abs(np.array(sa["passes"]) - np.array(sb["passes"]))
        i = int(np.argmax(gap))
        out["max_gap"] = {"width_um": _r(float(fine[i])), "gap": _r(float(gap[i])),
                          a.sample_id: _r(sa["passes"][i]), b.sample_id: _r(sb["passes"][i])}
    if result_chars(out) > MAX_RESULT_CHARS:      # keep the LLM context light
        for v in per.values():
            v["in_window"] = {k: f["passes"] for k, f in v["in_window"].items()}
        out["legend"] = "pass fractions (no membrane stretch needed)"
    return out


# ---------------------------------------------------------------------------
# 6. find_subpopulation
# ---------------------------------------------------------------------------

def find_subpopulation(sample_id: str, si_threshold: float) -> Dict:
    p = load_population(sample_id)
    t = float(si_threshold)
    if not (0.5 <= t <= 1.0):
        raise ToolError("si_threshold must be in [0.5, 1.0]")
    m = p.SI > t
    n = int(m.sum())
    out: Dict[str, Any] = {"sample_id": p.sample_id, "si_threshold": t, "n_cells": len(p.ids),
                           "n_sub": n, "fraction": _r(float(m.mean())), "provenance": "COMPUTED"}
    if n == 0:
        out["note"] = "No cell above this threshold."
        return out
    v3 = sweep_capillary(p.V[m], p.S[m], diameters=np.array([DISPLAY_REFERENCE_UM]))
    rest = ~m
    sub_idx = np.where(m)[0]
    # 3 examples: the sub-population cells closest to its own median SI
    order = sub_idx[np.argsort(np.abs(p.SI[sub_idx] - np.median(p.SI[sub_idx])))]
    out.update({
        "sub": {"mcd_um_p50": _r(float(np.median(p.MCD[m]))),
                "volume_fl_p50": _r(float(np.median(p.V[m]))),
                "si_p50": _r(float(np.median(p.SI[m]))),
                "blocked_at_3um": _r(v3["blocked"][0]),
                "passes_at_3um": _r(v3["passes"][0])},
        "rest": ({"mcd_um_p50": _r(float(np.median(p.MCD[rest]))),
                  "si_p50": _r(float(np.median(p.SI[rest])))} if rest.any() else None),
        "shape_classes": dict(Counter(p.shape_class[i] for i in sub_idx).most_common(4)),
        "example_cell_ids": [p.ids[i] for i in order[:3]],
    })
    return out


# ---------------------------------------------------------------------------
# 7. simulate_cell
# ---------------------------------------------------------------------------

def simulate_cell(sample_id: str, cell_id: str, diameter_um: float,
                  stiffness_hypothesis: Optional[float] = None) -> Dict:
    p = load_population(sample_id)
    if cell_id not in p.ids:
        raise ToolError(f"unknown cell_id {cell_id!r} in {p.sample_id}")
    D = float(diameter_um)
    if not (1.0 <= D <= 10.0):
        raise ToolError("diameter_um must be in [1, 10]")
    i = p.ids.index(cell_id)
    V, S = float(p.V[i]), float(p.S[i])
    st = float(stiffness_hypothesis) if stiffness_hypothesis is not None else None
    pr = passage(V, S, D, stiffness_hypothesis=st).to_dict()
    cap = capsule_shape(V, D)
    return {
        "sample_id": p.sample_id, "cell_id": cell_id, "shape_class": p.shape_class[i],
        "volume_fl": _r(V), "surface_um2": _r(S), "sphericity_index": _r(float(p.SI[i])),
        "passage": _r({k: v for k, v in pr.items() if k != "caveat"}),
        "caveat": pr.get("caveat") or "",
        "capsule": _r({k: cap[k] for k in ("radius_um", "cylinder_length_um", "total_length_um")}),
        "stiffness_provenance": "HYPOTHESIS" if st is not None else None,
    }


# ---------------------------------------------------------------------------
# 8. select_cells_for_display
# ---------------------------------------------------------------------------

def select_cells_for_display(sample_id: str, strategy: str,
                             diameter_um: float = DISPLAY_REFERENCE_UM) -> Dict:
    p = load_population(sample_id)
    D = float(diameter_um)
    if strategy == "typical":
        zv = (p.V - np.median(p.V)) / (np.std(p.V) or 1.0)
        zs = (p.SI - np.median(p.SI)) / (np.std(p.SI) or 1.0)
        order = np.argsort(zv ** 2 + zs ** 2)
        reason = "closest to the sample median volume and sphericity"
    elif strategy == "worst":
        order = np.argsort(-p.MCD)
        reason = "largest minimum cylindrical diameter (least surface reserve)"
    elif strategy == "borderline":
        order = np.argsort(np.abs(p.MCD - D))
        reason = f"minimum cylindrical diameter closest to the {D:g} µm channel"
    else:
        raise ToolError("strategy must be one of: typical, worst, borderline")
    picks = []
    for i in order[:2]:
        pr = passage(float(p.V[i]), float(p.S[i]), D)
        picks.append({"cell_id": p.ids[i], "shape_class": p.shape_class[i],
                      "volume_fl": _r(float(p.V[i])), "sphericity_index": _r(float(p.SI[i])),
                      "mcd_um": _r(float(p.MCD[i])), f"verdict_at_{D:g}um": pr.verdict,
                      "area_strain_needed": _r(pr.area_strain_needed)})
    return {"sample_id": p.sample_id, "strategy": strategy, "reference_width_um": D,
            "reason": reason, "cells": picks}


# ---------------------------------------------------------------------------
# 9. design_experiment
# ---------------------------------------------------------------------------

def design_experiment(sample_a: str, sample_b: str) -> Dict:
    a, b = load_population(sample_a), load_population(sample_b)
    exp = physics_design_experiment(_full_sweep(a), _full_sweep(b),
                                    label_a=a.sample_id, label_b=b.sample_id)
    exp["predicted_pass_fraction"] = {f"{k:g}" if isinstance(k, float) else str(k): v
                                      for k, v in exp["predicted_pass_fraction"].items()}
    return _r(exp, 4)


# ---------------------------------------------------------------------------
# JSON schemas (Messages API tool definitions)
# ---------------------------------------------------------------------------

_SID = {"type": "string", "description": "Sample id, e.g. synthetic_hs"}

TOOL_SCHEMAS: List[Dict] = [
    {"name": "list_samples",
     "description": "List available samples: id, label, source (synthetic/public_dataset), "
                    "whether a CBC exists, number of cells.",
     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "measure_sample",
     "description": "Data-quality summary of the image measurements (MEASURED): kept/excluded "
                    "cells, diameter quantiles and CV, central-pallor distribution, shape classes.",
     "input_schema": {"type": "object", "properties": {"sample_id": _SID},
                      "required": ["sample_id"], "additionalProperties": False}},
    {"name": "infer_geometry",
     "description": "Per-cell volume V (INFERRED, scaled on CBC MCV), surface S and sphericity "
                    "index SI (INFERRED from pallor), minimum cylindrical diameter MCD "
                    "(COMPUTED): quantiles, plus fraction of cells with SI above 0.8/0.85/0.9 "
                    "and an optional extra threshold. Also returns the model constants.",
     "input_schema": {"type": "object",
                      "properties": {"sample_id": _SID,
                                     "si_threshold": {"type": "number",
                                                      "description": "optional extra SI threshold"}},
                      "required": ["sample_id"], "additionalProperties": False}},
    {"name": "check_cbc_consistency",
     "description": "Cross-check CBC (CONSTRAINED) against the image: RDW-CV vs 3x diameter CV, "
                    "MCHC vs fraction of cells without pallor. Returns COHERENT/INCOHERENT flags.",
     "input_schema": {"type": "object", "properties": {"sample_id": _SID},
                      "required": ["sample_id"], "additionalProperties": False}},
    {"name": "sweep_channels",
     "description": "Capsule-model passage sweep (COMPUTED). For each sample: D50 (width where "
                    "50% pass without stretch), pass fractions at 2.5/3.0/3.5/4.0 µm, and "
                    "passes/under_strain/blocked at 7 widths in [d_min, d_max]. With 2 samples, "
                    "also the width of maximum difference.",
     "input_schema": {"type": "object",
                      "properties": {"sample_ids": {"type": "array", "items": {"type": "string"},
                                                    "minItems": 1, "maxItems": 3},
                                     "d_min": {"type": "number", "description": "µm, >= 1.5"},
                                     "d_max": {"type": "number", "description": "µm, <= 8"}},
                      "required": ["sample_ids", "d_min", "d_max"],
                      "additionalProperties": False}},
    {"name": "find_subpopulation",
     "description": "Isolate cells with SI above a threshold: fraction, median MCD/V/SI, "
                    "fraction blocked at 3 µm, shape classes, 3 example cell ids.",
     "input_schema": {"type": "object",
                      "properties": {"sample_id": _SID,
                                     "si_threshold": {"type": "number",
                                                      "description": "between 0.5 and 1.0"}},
                      "required": ["sample_id", "si_threshold"], "additionalProperties": False}},
    {"name": "simulate_cell",
     "description": "Passage verdict for one cell in one channel width (PASSES / "
                    "PASSES_UNDER_STRAIN / BLOCKED), area strain needed, MCD, capsule shape. "
                    "stiffness_hypothesis (x normal) is only carried as a HYPOTHESIS caveat.",
     "input_schema": {"type": "object",
                      "properties": {"sample_id": _SID, "cell_id": {"type": "string"},
                                     "diameter_um": {"type": "number"},
                                     "stiffness_hypothesis": {"type": "number"}},
                      "required": ["sample_id", "cell_id", "diameter_um"],
                      "additionalProperties": False}},
    {"name": "select_cells_for_display",
     "description": "Pick cells for the 3D view: strategy typical (median V and SI), worst "
                    "(largest MCD) or borderline (MCD closest to the reference width, "
                    "default 3 µm). Returns ids and the reason.",
     "input_schema": {"type": "object",
                      "properties": {"sample_id": _SID,
                                     "strategy": {"type": "string",
                                                  "enum": ["typical", "worst", "borderline"]},
                                     "diameter_um": {"type": "number"}},
                      "required": ["sample_id", "strategy"], "additionalProperties": False}},
    {"name": "design_experiment",
     "description": "Turn the two passage curves into a falsifiable microfluidic experiment: "
                    "most discriminating width, flanking widths, predicted pass fractions, "
                    "cells per sample for 80% power.",
     "input_schema": {"type": "object",
                      "properties": {"sample_a": _SID, "sample_b": _SID},
                      "required": ["sample_a", "sample_b"], "additionalProperties": False}},
    {"name": "submit_report",
     "description": "Submit the final report (contract 4.5). number_guard checks every number "
                    "in it against this run's tool results; if any number is unverified the "
                    "report is REFUSED and the list is returned: fix and resubmit. Numbers you "
                    "chose yourself must appear in findings[].numbers with provenance HYPOTHESIS.",
     "input_schema": {
         "type": "object",
         "properties": {"report": {
             "type": "object",
             "properties": {
                 "title": {"type": "string"},
                 "summary": {"type": "string"},
                 "findings": {"type": "array", "items": {
                     "type": "object",
                     "properties": {
                         "text": {"type": "string"},
                         "numbers": {"type": "array", "items": {
                             "type": "object",
                             "properties": {
                                 "value": {"type": "number"},
                                 "unit": {"type": "string"},
                                 "provenance": {"type": "string",
                                                "enum": ["MEASURED", "CONSTRAINED", "INFERRED",
                                                         "COMPUTED", "HYPOTHESIS"]},
                                 "tool_call_id": {"type": ["string", "null"]}},
                             "required": ["value", "unit", "provenance", "tool_call_id"]}}},
                     "required": ["text", "numbers"]}},
                 "consistency_flags": {"type": "array", "items": {"type": "object"}},
                 "experiment": {"type": ["object", "null"],
                                "description": "the design_experiment output, unchanged"},
                 "limitations": {"type": "array", "items": {"type": "string"}}},
             "required": ["title", "summary", "findings", "limitations"]}},
         "required": ["report"], "additionalProperties": False}},
]

TOOL_NAMES = [t["name"] for t in TOOL_SCHEMAS]

_FUNCS: Dict[str, Callable[..., Dict]] = {
    "list_samples": list_samples,
    "measure_sample": measure_sample,
    "infer_geometry": infer_geometry,
    "check_cbc_consistency": check_cbc_consistency,
    "sweep_channels": sweep_channels,
    "find_subpopulation": find_subpopulation,
    "simulate_cell": simulate_cell,
    "select_cells_for_display": select_cells_for_display,
    "design_experiment": design_experiment,
}


# ---------------------------------------------------------------------------
# Run context: executes tools and remembers every result (for number_guard)
# ---------------------------------------------------------------------------

class ToolRunner:
    """Executes tools for one agent run and keeps every tool result for number_guard."""

    def __init__(self) -> None:
        self.results: Dict[str, Any] = {}      # tool_call_id -> output (successful calls)
        self.inputs: Dict[str, Dict] = {}      # tool_call_id -> input
        self.accepted_report: Optional[Dict] = None

    def execute(self, name: str, tool_input: Dict, call_id: str) -> (Dict, bool):
        """Return (output, is_error). Never raises for tool-level problems."""
        tool_input = tool_input or {}
        self.inputs[call_id] = tool_input
        try:
            if name == "submit_report":
                out = self._submit_report(tool_input)
                return out, not out.get("accepted", False)
            fn = _FUNCS.get(name)
            if fn is None:
                raise ToolError(f"unknown tool {name!r}")
            out = fn(**tool_input)
        except ToolError as e:
            return {"error": str(e)}, True
        except TypeError as e:
            return {"error": f"bad arguments for {name}: {e}"}, True
        except Exception as e:  # noqa: BLE001 - surface to the agent, keep the run alive
            return {"error": f"{type(e).__name__}: {e}"}, True
        self.results[call_id] = out
        return out, False

    def _submit_report(self, tool_input: Dict) -> Dict:
        from backend.agent.number_guard import check_report
        report = tool_input.get("report")
        if not isinstance(report, dict):
            raise ToolError("submit_report needs {'report': {...}}")
        for k in ("title", "summary", "findings", "limitations"):
            if k not in report:
                raise ToolError(f"report is missing '{k}'")
        guard = check_report(report, self.results)
        if guard["unverified"] > 0:
            return {"accepted": False, "number_guard": {"checked": guard["checked"],
                                                        "unverified": guard["unverified"]},
                    "unverified_numbers": guard["unverified_items"][:15],
                    "instruction": ("Each listed number is not found (to 2 significant figures) "
                                    "in any tool result of this run. Replace it by a tool value, "
                                    "remove it, or declare it in findings[].numbers with "
                                    "provenance HYPOTHESIS. Then call submit_report again.")}
        report = dict(report)
        report.setdefault("consistency_flags", [])
        report.setdefault("experiment", None)
        report["number_guard"] = {"checked": guard["checked"], "unverified": 0}
        self.accepted_report = report
        return {"accepted": True, "number_guard": report["number_guard"]}


def result_chars(output: Any) -> int:
    return len(json.dumps(output, ensure_ascii=False, separators=(",", ":")))
