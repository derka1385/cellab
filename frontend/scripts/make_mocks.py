"""
Build the frontend mock files (contracts 4.1 to 4.5) into frontend/public/mocks/.

Run from the repo root:
    python frontend/scripts/make_mocks.py

What it does
- Copies every sample under backend/data/samples/<id>/ (sample.json, cbc.json,
  population.json, image.png / overlay.png if present) into mocks/samples/<id>/.
- Writes mocks/samples.json (the /api/samples listing).
- Writes a few cell meshes per sample with mesh_cell() (mocks/samples/<id>/meshes/<cell>.json).
  Any other cell falls back to the TypeScript port of mesh_cell in the frontend.
- Writes a realistic mock agent trace (mocks/replay_mock.jsonl, contract 4.4) and its
  report (mocks/runs/r_mock/report.json, contract 4.5). Every number comes from the
  physics core, so the mock obeys the "no invented number" rule.
- mocks/replay_main.jsonl = copy of demo/replay_main.jsonl if it exists, else the mock trace.

Only writes inside frontend/.
"""
from __future__ import annotations

import json
import math
import shutil
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backend.physics.celllab_physics import (  # noqa: E402
    capsule_shape,
    design_experiment,
    mesh_cell,
    passage,
    sweep_capillary,
    d50,
)

SAMPLES_SRC = ROOT / "backend" / "data" / "samples"
MOCKS = ROOT / "frontend" / "public" / "mocks"
A_ID, B_ID = "synthetic_healthy", "synthetic_hs"


def rnd(obj, nd=4):
    if isinstance(obj, float):
        return None if math.isnan(obj) else round(obj, nd)
    if isinstance(obj, (np.floating,)):
        return rnd(float(obj), nd)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, dict):
        return {str(k): rnd(v, nd) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [rnd(v, nd) for v in obj]
    return obj


def write(p: Path, data) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def copy_samples() -> dict:
    pops = {}
    listing = []
    for d in sorted(SAMPLES_SRC.iterdir()):
        if not (d / "sample.json").exists() or not (d / "population.json").exists():
            continue
        out = MOCKS / "samples" / d.name
        out.mkdir(parents=True, exist_ok=True)
        for f in ("sample.json", "cbc.json", "population.json", "image.png", "overlay.png"):
            if (d / f).exists():
                shutil.copy(d / f, out / f)
        sample = json.loads((d / "sample.json").read_text())
        pop = json.loads((d / "population.json").read_text())
        pops[d.name] = (sample, pop)
        listing.append({
            "sample_id": d.name,
            "label": sample.get("label", d.name),
            "has_cbc": (d / "cbc.json").exists(),
            "has_image": (d / "image.png").exists(),
            "n_cells": len(pop["cells"]),
            "synthetic": bool(pop.get("synthetic")),
            "source": sample.get("source"),
        })
    write(MOCKS / "samples.json", listing)
    return pops


def vs(pop):
    V = np.array([c["volume_fl"]["value"] for c in pop["cells"]])
    S = np.array([c["surface_um2"]["value"] for c in pop["cells"]])
    SI = np.array([c["sphericity_index"]["value"] for c in pop["cells"]])
    ids = [c["cell_id"] for c in pop["cells"]]
    return V, S, SI, ids


def pick_display_cells(pop, k_random=6):
    V, S, SI, ids = vs(pop)
    mcd = np.array([c["mcd_um"]["value"] for c in pop["cells"]])
    picks = {
        ids[int(np.argmin(np.abs(SI - np.median(SI))))]: "typical: SI closest to the sample median",
        ids[int(np.argmax(SI))]: "worst: highest sphericity index",
        ids[int(np.argmin(np.abs(mcd - 3.0)))]: "borderline: MCD closest to 3.0 µm",
    }
    rng = np.random.default_rng(0)
    for i in rng.choice(len(ids), size=min(k_random, len(ids)), replace=False):
        picks.setdefault(ids[int(i)], "random")
    return picks


def write_meshes(sid, pop):
    picks = pick_display_cells(pop)
    for cid in picks:
        sh = pop["cell_extra"][cid]["shape"]
        m = mesh_cell(sh["morph_t"], sh["radius_um"])
        m["vertices"] = [[round(x, 3) for x in v] for v in m["vertices"]]
        m["cell_id"] = cid
        m["provenance"] = "INFERRED"
        write(MOCKS / "samples" / sid / "meshes" / f"{cid}.json", m)
    return picks


def quantiles(x):
    q = np.quantile(x, [0.1, 0.5, 0.9])
    return {"p10": float(q[0]), "p50": float(q[1]), "p90": float(q[2])}


def make_trace(pops):
    sa, pa = pops[A_ID]
    sb, pb = pops[B_ID]
    Va, Sa, SIa, ida = vs(pa)
    Vb, Sb, SIb, idb = vs(pb)
    D = np.round(np.arange(2.0, 5.0 + 1e-9, 0.025), 3)
    swa, swb = sweep_capillary(Va, Sa, D), sweep_capillary(Vb, Sb, D)
    d50a, d50b = d50(swa), d50(swb)
    thr = 0.85
    fa, fb = float(np.mean(SIa > thr)), float(np.mean(SIb > thr))
    sub = SIb > thr
    mcd_b = np.array([c["mcd_um"]["value"] for c in pb["cells"]])
    worst = idb[int(np.argmax(SIb))]
    exp = design_experiment(swa, swb, label_a=A_ID, label_b=B_ID)
    d_star = exp["most_discriminating_width_um"]
    iw = idb.index(worst)
    pr = passage(float(Vb[iw]), float(Sb[iw]), d_star).to_dict()
    cap = capsule_shape(float(Vb[iw]), d_star)

    def at(sw, d):
        return float(np.interp(d, sw["diameters_um"], sw["passes"]))

    ev = []
    t = [0.0]

    def push(dt, **e):
        t[0] += dt
        ev.append({"seq": len(ev) + 1, "t": round(t[0], 1), **rnd(e)})

    push(0.0, type="plan", text=("I will compare both samples: infer cell geometry, check CBC "
                                 "coherence, look for a spherical subpopulation, then sweep "
                                 "channel widths and design a falsifiable microfluidic test."))
    push(1.1, type="tool_call", id="tc_01", tool="list_samples", input={})
    push(0.6, type="tool_result", id="tc_01", output={"samples": [
        {"sample_id": A_ID, "n_cells": len(ida), "has_cbc": True, "synthetic": True},
        {"sample_id": B_ID, "n_cells": len(idb), "has_cbc": True, "synthetic": True}]})
    push(1.3, type="tool_call", id="tc_02", tool="infer_geometry", input={"sample_id": A_ID})
    push(1.0, type="tool_result", id="tc_02", output={
        "n_cells": len(ida), "si": quantiles(SIa), "volume_fl": quantiles(Va),
        "fraction_si_above_0.85": fa})
    push(0.9, type="tool_call", id="tc_03", tool="infer_geometry", input={"sample_id": B_ID})
    push(1.0, type="tool_result", id="tc_03", output={
        "n_cells": len(idb), "si": quantiles(SIb), "volume_fl": quantiles(Vb),
        "fraction_si_above_0.85": fb})
    push(1.4, type="message", text=("Sample B has a heavy upper tail in sphericity (p90 above "
                                    "0.85). I will check whether the CBC agrees before trusting it."))
    push(0.8, type="tool_call", id="tc_04", tool="check_cbc_consistency", input={"sample_id": B_ID})
    push(0.7, type="tool_result", id="tc_04", output={"flags": pb["consistency"]})
    push(1.2, type="tool_call", id="tc_05", tool="find_subpopulation",
         input={"sample_id": B_ID, "si_threshold": thr})
    push(0.8, type="tool_result", id="tc_05", output={
        "fraction": fb, "n_cells": int(sub.sum()),
        "median_mcd_um": float(np.median(mcd_b[sub])) if sub.any() else None,
        "example_cell_ids": [idb[i] for i in np.argsort(-SIb)[:3]]})
    push(1.3, type="tool_call", id="tc_06", tool="sweep_channels",
         input={"sample_ids": [A_ID, B_ID], "d_min": 2.0, "d_max": 5.0})
    push(1.5, type="tool_result", id="tc_06", output={
        "d50_um": {A_ID: d50a, B_ID: d50b},
        "pass_fraction": {f"{d:.1f}": {A_ID: at(swa, d), B_ID: at(swb, d)}
                          for d in (2.5, 3.0, 3.5, 4.0)}})
    push(1.2, type="message", text=("The curves separate most between 3 and 3.5 µm. "
                                    "I will design the experiment around the widest gap."))
    push(0.9, type="tool_call", id="tc_07", tool="design_experiment",
         input={"sample_a": A_ID, "sample_b": B_ID})
    push(1.1, type="tool_result", id="tc_07", output=exp)
    push(0.8, type="tool_call", id="tc_08", tool="select_cells_for_display",
         input={"sample_id": B_ID, "strategy": "worst"})
    push(0.5, type="tool_result", id="tc_08", output={
        "cell_ids": [worst], "reason": "highest sphericity index in the sample"})
    push(0.7, type="tool_call", id="tc_09", tool="simulate_cell",
         input={"sample_id": B_ID, "cell_id": worst, "diameter_um": d_star})
    push(0.6, type="tool_result", id="tc_09", output={**pr, "capsule": cap})

    p_a, p_b = at(swa, d_star), at(swb, d_star)
    report = {
        "title": f"Sample B has a spherical subpopulation that fails {d_star:.2f} µm channels",
        "summary": (f"In this synthetic demo pair, {fb:.0%} of cells in sample B have a sphericity "
                    f"index above {thr}, versus {fa:.0%} in sample A. The simulated passage curves "
                    f"give D50 = {d50a:.2f} µm (A) and {d50b:.2f} µm (B). This is a hypothesis to "
                    "test, not a diagnosis."),
        "findings": [
            {"text": f"{fb:.0%} of cells in sample B have a sphericity index above {thr}, versus {fa:.0%} in sample A.",
             "numbers": [
                 {"value": fb, "unit": "fraction", "provenance": "INFERRED", "tool_call_id": "tc_05"},
                 {"value": thr, "unit": "", "provenance": "HYPOTHESIS", "tool_call_id": None},
                 {"value": fa, "unit": "fraction", "provenance": "INFERRED", "tool_call_id": "tc_02"}]},
            {"text": f"Half of the cells pass without membrane strain at {d50a:.2f} µm in A and {d50b:.2f} µm in B.",
             "numbers": [
                 {"value": d50a, "unit": "µm", "provenance": "COMPUTED", "tool_call_id": "tc_06"},
                 {"value": d50b, "unit": "µm", "provenance": "COMPUTED", "tool_call_id": "tc_06"}]},
            {"text": f"At {d_star:.2f} µm the predicted pass fraction is {p_a:.0%} for A versus {p_b:.0%} for B.",
             "numbers": [
                 {"value": d_star, "unit": "µm", "provenance": "COMPUTED", "tool_call_id": "tc_07"},
                 {"value": p_a, "unit": "fraction", "provenance": "COMPUTED", "tool_call_id": "tc_07"},
                 {"value": p_b, "unit": "fraction", "provenance": "COMPUTED", "tool_call_id": "tc_07"}]},
        ],
        "consistency_flags": pb["consistency"],
        "experiment": exp,
        "limitations": ["Sphericity is inferred from central pallor.",
                        "No mechanical simulation: the passage verdict is geometric only.",
                        "Synthetic demo populations, not patient data."],
        "number_guard": {"checked": 9, "unverified": 0},
    }
    push(1.6, type="tool_call", id="tc_10", tool="submit_report", input={"report": report})
    push(0.5, type="tool_result", id="tc_10", output={"accepted": True, "number_guard": report["number_guard"]})
    push(0.4, type="report", report_path="data/runs/r_mock/report.json")
    return ev, rnd(report)


def main():
    pops = copy_samples()
    if A_ID not in pops or B_ID not in pops:
        sys.exit(f"Need {A_ID} and {B_ID} in {SAMPLES_SRC} (run: python -m backend.pipeline --synthetic)")
    display = {sid: write_meshes(sid, pop) for sid, (_, pop) in pops.items()}
    write(MOCKS / "display_cells.json", display)
    ev, report = make_trace(pops)
    (MOCKS / "replay_mock.jsonl").write_text("\n".join(json.dumps(e, ensure_ascii=False) for e in ev) + "\n")
    write(MOCKS / "runs" / "r_mock" / "report.json", report)
    demo = ROOT / "demo" / "replay_main.jsonl"
    if demo.exists():
        shutil.copy(demo, MOCKS / "replay_main.jsonl")
        # Copy the report the recorded trace points to, if it is on disk.
        for line in demo.read_text().splitlines():
            if '"report"' in line and "report_path" in line:
                rp = json.loads(line)["report_path"]
                src = (ROOT / "backend" / rp) if not (ROOT / rp).exists() else ROOT / rp
                if src.exists():
                    dst = MOCKS / Path(rp).relative_to("data") if rp.startswith("data/") else MOCKS / rp
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy(src, dst)
        print("replay_main.jsonl <- demo/replay_main.jsonl")
    else:
        shutil.copy(MOCKS / "replay_mock.jsonl", MOCKS / "replay_main.jsonl")
        print("replay_main.jsonl <- mock trace (demo/replay_main.jsonl not found yet)")
    print("samples:", list(pops), "| display cells:", {k: len(v) for k, v in display.items()},
          "| trace events:", len(ev))


if __name__ == "__main__":
    main()
