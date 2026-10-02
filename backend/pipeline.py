"""
CellLab pipeline: sample.json + cbc.json -> population.json (contract 4.3).

Also generates the synthetic demo samples (synthetic_healthy, synthetic_hs) that unblock
the frontend and agent before real vision output exists.

Usage (from repo root):
    python -m backend.pipeline --synthetic          # (re)write both synthetic samples
    python -m backend.pipeline <sample_id> [--force] # build/refresh population.json
    python -m backend.pipeline --all [--force]       # every sample under data/samples
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from backend.physics.celllab_physics import (
    CBC,
    PALLOR_RATIO_NORMAL,
    SI_DISCOCYTE,
    SI_SPHEROCYTE,
    CellMeasurement,
    Tagged,
    cbc_consistency,
    d50,
    infer_population,
    passage,
    shape_for,
    sweep_capillary,
    synthetic_population,
)

SAMPLES_DIR = Path(__file__).resolve().parent / "data" / "samples"
SWEEP_DIAMETERS = np.round(np.arange(2.0, 5.0 + 1e-9, 0.025), 3)   # 121 points
PASSAGE_REF_UM = 3.0
NDIGITS = 4


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _round(obj: Any, nd: int = NDIGITS) -> Any:
    """Recursively round floats (keeps JSON small for the frontend). NaN -> None."""
    if isinstance(obj, float):
        return None if math.isnan(obj) or math.isinf(obj) else round(obj, nd)
    if isinstance(obj, (np.floating,)):
        return _round(float(obj), nd)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _round(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v, nd) for v in obj]
    return obj


def _read_json(p: Path) -> Dict:
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json(p: Path, data: Dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(_round(data), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(p)


def sample_dir(sample_id: str) -> Path:
    return SAMPLES_DIR / sample_id


# ---------------------------------------------------------------------------
# build_population
# ---------------------------------------------------------------------------

def build_population(sample_id: str, force: bool = False, write: bool = True) -> Dict:
    """
    Read sample.json + cbc.json, return (and cache to disk) population.json.
    Cached on disk: recomputed only if missing, older than its inputs, or force=True.
    """
    d = sample_dir(sample_id)
    pop_path = d / "population.json"
    s_path, c_path = d / "sample.json", d / "cbc.json"
    if (not force and pop_path.exists()
            and pop_path.stat().st_mtime >= max(s_path.stat().st_mtime, c_path.stat().st_mtime)):
        return _read_json(pop_path)

    sample = _read_json(s_path)
    cbc_raw = _read_json(c_path)
    cbc = CBC(mcv_fl=float(cbc_raw["mcv_fl"]),
              rdw_cv_pct=cbc_raw.get("rdw_cv_pct"),
              mchc_g_dl=cbc_raw.get("mchc_g_dl"))
    px_scale = sample.get("pixel_size_um")

    kept = [c for c in sample["cells"] if not c.get("excluded", False)]
    if not kept:
        raise ValueError(f"{sample_id}: no non-excluded cells")
    meas = [CellMeasurement(cell_id=c["cell_id"],
                            area_um2=float(c["area"]) * (px_scale ** 2 if px_scale else 1.0),
                            diameter_um=float(c["diameter"]) * (px_scale if px_scale else 1.0),
                            circularity=float(c["circularity"]),
                            pallor_ratio=float(c["pallor_ratio"]),
                            shape_class=c.get("shape_class") or "unknown")
            for c in kept]

    cells = infer_population(meas, cbc)
    if not px_scale:
        # Physics core labels these µm; with no pixel calibration they are pixels.
        for c in cells:
            m = c["measured"]
            m["area_um2"]["unit"] = "px²"
            m["area_um2"]["note"] = "pixel units (pixel_size_um is null); only ratios are used"
            m["diameter_um"]["unit"] = "px"
            m["diameter_um"]["note"] = "pixel units (pixel_size_um is null); only ratios are used"

    V = np.array([c["volume_fl"]["value"] for c in cells])
    S = np.array([c["surface_um2"]["value"] for c in cells])

    cell_extra: Dict[str, Dict] = {}
    for c, v, s in zip(cells, V, S):
        sh = shape_for(float(v), float(s))
        pr = passage(float(v), float(s), PASSAGE_REF_UM)
        cell_extra[c["cell_id"]] = {
            "shape": {"morph_t": sh["morph_t"], "radius_um": sh["radius_um"],
                      "provenance": "INFERRED"},
            "passage_at_3um": {"verdict": pr.verdict,
                               "area_strain_needed": pr.area_strain_needed,
                               "mcd_um": pr.mcd_um,
                               "provenance": "COMPUTED"},
        }

    sweep = sweep_capillary(V, S, diameters=SWEEP_DIAMETERS)
    d50_val = d50(sweep)

    pop = {
        "sample_id": sample_id,
        "cells": cells,
        "cell_extra": cell_extra,
        "sweep": sweep,
        "d50_um": d50_val,
        # Extension (not in contract 4.3): tagged version of d50_um.
        "d50": Tagged(d50_val, "µm", "COMPUTED",
                      "channel diameter where 50 % of cells pass without membrane strain"
                      ).to_dict() if not math.isnan(d50_val) else
               {"value": None, "unit": "µm", "provenance": "COMPUTED",
                "note": "fewer than 50 % of cells pass even at 5 µm"},
        "consistency": cbc_consistency(meas, cbc),
        "synthetic": sample.get("source") == "synthetic",
        "n_cells": len(cells),
        "n_excluded": len(sample["cells"]) - len(kept),
    }
    pop = _round(pop)
    if write:
        _write_json(pop_path, pop)
    return pop


# ---------------------------------------------------------------------------
# synthetic samples
# ---------------------------------------------------------------------------

SYNTHETIC_SPECS = {
    "synthetic_healthy": {
        "kind": "healthy", "seed": 11,
        "label": "Synthetic healthy population (not patient data)",
        "cbc": {"mcv_fl": 90.0, "rdw_cv_pct": 12.8, "mchc_g_dl": 34.0},
    },
    "synthetic_hs": {
        "kind": "spherocytosis", "seed": 12,
        "label": "Synthetic spherocytosis-like population (not patient data)",
        "cbc": {"mcv_fl": 84.0, "rdw_cv_pct": 17.5, "mchc_g_dl": 37.2},
    },
}
N_SYNTH = 300
MEDIAN_AREA_PX = 1500.0


def _pallor_from_si(si: np.ndarray) -> np.ndarray:
    """Inverse of si_from_pallor, clipped to [0, PALLOR_RATIO_NORMAL]."""
    w = (SI_SPHEROCYTE - si) / (SI_SPHEROCYTE - SI_DISCOCYTE)
    return np.clip(w * PALLOR_RATIO_NORMAL, 0.0, PALLOR_RATIO_NORMAL)


def make_synthetic_sample(sample_id: str, n: int = N_SYNTH) -> Dict:
    spec = SYNTHETIC_SPECS[sample_id]
    pop = synthetic_population(spec["kind"], n=n, seed=spec["seed"])
    V, SI = pop["V"], pop["SI"]
    k_sph = int(0.3 * n) if spec["kind"] == "spherocytosis" else 0
    classes = ["normal"] * (n - k_sph) + ["spherocyte"] * k_sph

    raw_area = V ** (2 / 3)
    area = raw_area * (MEDIAN_AREA_PX / float(np.median(raw_area)))
    diam = 2.0 * np.sqrt(area / math.pi)
    rng = np.random.default_rng(spec["seed"] + 1000)
    circ = np.clip(rng.normal(0.9, 0.03, n), 0.6, 1.0)
    pallor = _pallor_from_si(SI)

    # Fake layout on a grid so the frontend can draw something; there is no real image.
    order = rng.permutation(n)
    cols = int(math.ceil(math.sqrt(n)))
    pitch = float(diam.max()) * 1.25
    ang = np.linspace(0, 2 * math.pi, 24, endpoint=False)
    cells = []
    for slot, i in enumerate(order):
        cx = (slot % cols + 0.5) * pitch
        cy = (slot // cols + 0.5) * pitch
        r = diam[i] / 2
        contour = [[round(cx + r * math.cos(a), 1), round(cy + r * math.sin(a), 1)] for a in ang]
        cells.append({
            "cell_id": f"c{i:03d}",
            "centroid_px": [round(cx, 1), round(cy, 1)],
            "bbox_px": [int(cx - r), int(cy - r), int(math.ceil(2 * r)), int(math.ceil(2 * r))],
            "contour_px": contour,
            "area": float(area[i]),
            "diameter": float(diam[i]),
            "circularity": float(circ[i]),
            "pallor_ratio": float(pallor[i]),
            "shape_class": classes[i],
            "shape_class_source": "none",
            "excluded": False,
            "exclusion_reason": None,
        })
    cells.sort(key=lambda c: c["cell_id"])
    return {
        "sample_id": sample_id,
        "label": spec["label"],
        "image_path": None,
        "pixel_size_um": None,
        "source": "synthetic",
        "note": (f"Generated by synthetic_population('{spec['kind']}', n={n}, "
                 f"seed={spec['seed']}). Area ∝ V^(2/3) in arbitrary pixels; pallor obtained by "
                 "inverting si_from_pallor. No image."),
        "cells": cells,
    }


def write_synthetic_samples() -> List[str]:
    out = []
    for sid, spec in SYNTHETIC_SPECS.items():
        d = sample_dir(sid)
        _write_json(d / "sample.json", make_synthetic_sample(sid))
        _write_json(d / "cbc.json", {**spec["cbc"], "source": "demo",
                                     "note": "Demo values, not patient data"})
        build_population(sid, force=True)
        out.append(sid)
    return out


def list_samples() -> List[str]:
    if not SAMPLES_DIR.exists():
        return []
    return sorted(p.name for p in SAMPLES_DIR.iterdir()
                  if (p / "sample.json").exists() and (p / "cbc.json").exists())


def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="CellLab pipeline")
    ap.add_argument("sample_id", nargs="?")
    ap.add_argument("--synthetic", action="store_true", help="write synthetic samples")
    ap.add_argument("--all", action="store_true", help="build every sample")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    ids: List[str] = []
    if a.synthetic:
        ids += write_synthetic_samples()
    if a.all:
        ids += [s for s in list_samples() if s not in ids]
    if a.sample_id:
        ids.append(a.sample_id)
    if not ids:
        ap.error("give a sample_id, --synthetic or --all")
    for sid in ids:
        pop = build_population(sid, force=a.force)
        cons = ", ".join(f"{c['check']}={c['status']}" for c in pop["consistency"])
        meanV = float(np.mean([c["volume_fl"]["value"] for c in pop["cells"]]))
        print(f"{sid}: n={pop['n_cells']} meanV={meanV:.2f} fL d50={pop['d50_um']} µm "
              f"synthetic={pop['synthetic']} [{cons}]")


if __name__ == "__main__":
    main()
