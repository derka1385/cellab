"""
CellLab API (contract section 6).

Run from the repo root:
    uvicorn backend.api.app:app --reload

Populations are cached on disk (population.json, built by backend.pipeline) and in memory,
so the per-cell routes (passage, mesh) are pure lookups + closed-form geometry.
"""
from __future__ import annotations

import importlib
import json
import re
import tempfile
import threading
import time
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from backend.physics.celllab_physics import (capsule_shape, mesh_cell, passage, sphere_diameter,
                                             write_stl)
from backend.pipeline import SAMPLES_DIR, _read_json, build_population, list_samples

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "backend" / "data" / "runs"
DEMO_DIR = REPO_ROOT / "demo"
STL_SCALE = 5.0          # µm -> mm x5 = x5000 physical scale (~4 cm object)
_SAFE_ID = re.compile(r"^[A-Za-z0-9_.-]+$")

app = FastAPI(title="CellLab API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# sample / population cache
# ---------------------------------------------------------------------------

_pop_cache: Dict[str, Dict[str, Any]] = {}   # sample_id -> {"mtime", "pop", "index"}
_pop_lock = threading.Lock()


def _check_id(x: str) -> str:
    if not _SAFE_ID.match(x) or x.startswith("."):
        raise HTTPException(400, f"invalid id: {x!r}")
    return x


def _sample_dir(sample_id: str) -> Path:
    d = SAMPLES_DIR / _check_id(sample_id)
    if not (d / "sample.json").exists() or not (d / "cbc.json").exists():
        raise HTTPException(404, f"unknown sample: {sample_id}")
    return d


def get_population(sample_id: str) -> Dict[str, Any]:
    """Population + per-cell index, cached in memory and invalidated on file change."""
    d = _sample_dir(sample_id)
    pop_path = d / "population.json"
    with _pop_lock:
        entry = _pop_cache.get(sample_id)
        mtime = pop_path.stat().st_mtime if pop_path.exists() else None
        inputs_mtime = max((d / "sample.json").stat().st_mtime, (d / "cbc.json").stat().st_mtime)
        if entry and mtime is not None and mtime == entry["mtime"] and mtime >= inputs_mtime:
            return entry
        try:
            pop = build_population(sample_id)       # uses the on-disk cache if fresh
        except Exception as e:                      # noqa: BLE001
            raise HTTPException(500, f"population build failed for {sample_id}: {e}") from e
        index = {c["cell_id"]: c for c in pop["cells"]}
        entry = {"mtime": pop_path.stat().st_mtime if pop_path.exists() else None,
                 "pop": pop, "index": index}
        _pop_cache[sample_id] = entry
        return entry


def _cell(sample_id: str, cell_id: str) -> Dict[str, Any]:
    entry = get_population(sample_id)
    c = entry["index"].get(cell_id)
    if c is None:
        raise HTTPException(404, f"unknown or excluded cell: {sample_id}/{cell_id}")
    extra = entry["pop"]["cell_extra"].get(cell_id, {})
    return {"cell": c, "extra": extra}


@lru_cache(maxsize=512)
def _mesh(morph_t: float, radius_um: float) -> Dict:
    m = mesh_cell(morph_t, radius_um)
    return {"vertices": [[round(x, 4) for x in v] for v in m["vertices"]],
            "faces": m["faces"], "units": m["units"]}


def _image_path(sample_id: str, sample: Optional[Dict] = None) -> Optional[Path]:
    d = SAMPLES_DIR / sample_id
    if (d / "image.png").exists():
        return d / "image.png"
    ip = (sample or {}).get("image_path")
    if ip:
        for base in (REPO_ROOT / "backend", REPO_ROOT, d):
            p = (base / ip).resolve()
            if p.exists() and REPO_ROOT in p.parents:
                return p
    return None


# ---------------------------------------------------------------------------
# routes: samples
# ---------------------------------------------------------------------------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/samples")
def samples() -> List[Dict[str, Any]]:
    out = []
    for sid in list_samples():
        d = SAMPLES_DIR / sid
        try:
            s = _read_json(d / "sample.json")
            cbc = _read_json(d / "cbc.json")
        except Exception:                           # noqa: BLE001
            continue
        row = {"sample_id": sid, "label": s.get("label", sid), "source": s.get("source"),
               "synthetic": s.get("source") == "synthetic", "cbc_source": cbc.get("source"),
               "has_image": _image_path(sid, s) is not None,
               "n_cells": sum(1 for c in s.get("cells", []) if not c.get("excluded"))}
        try:
            row["d50"] = get_population(sid)["pop"].get("d50")
        except HTTPException:
            row["d50"] = None
        out.append(row)
    return out


@app.get("/api/samples/{sample_id}")
def sample_detail(sample_id: str) -> Dict[str, Any]:
    d = _sample_dir(sample_id)
    return {"sample": _read_json(d / "sample.json"),
            "cbc": _read_json(d / "cbc.json"),
            "population": get_population(sample_id)["pop"]}


@app.get("/api/samples/{sample_id}/image")
def sample_image(sample_id: str):
    d = _sample_dir(sample_id)
    p = _image_path(sample_id, _read_json(d / "sample.json"))
    if p is None:
        raise HTTPException(404, f"no image for sample {sample_id} (synthetic samples have none)")
    return FileResponse(p)


# ---------------------------------------------------------------------------
# routes: per cell
# ---------------------------------------------------------------------------

@app.get("/api/samples/{sample_id}/cells/{cell_id}/mesh")
def cell_mesh(sample_id: str, cell_id: str) -> Dict[str, Any]:
    x = _cell(sample_id, _check_id(cell_id))
    sh = x["extra"].get("shape")
    if not sh:
        raise HTTPException(500, "shape missing in population.json; rebuild with --force")
    m = _mesh(float(sh["morph_t"]), float(sh["radius_um"]))
    return {"sample_id": sample_id, "cell_id": cell_id,
            "shape": sh, **m, "provenance": "INFERRED",
            "note": "axisymmetric shape matched to the cell's inferred V and sphericity index"}


def _T(v: float, unit: str, prov: str, note: str = "") -> Dict[str, Any]:
    return {"value": round(float(v), 4), "unit": unit, "provenance": prov, "note": note}


@app.get("/api/samples/{sample_id}/cells/{cell_id}/passage")
def cell_passage(sample_id: str, cell_id: str,
                 d: float = Query(3.0, gt=0.5, le=20.0, description="channel diameter, µm"),
                 stiffness: float = Query(1.0, gt=0.0, le=100.0,
                                          description="HYPOTHESIS: x normal stiffness")):
    x = _cell(sample_id, _check_id(cell_id))
    c = x["cell"]
    V, S = float(c["volume_fl"]["value"]), float(c["surface_um2"]["value"])
    # The capsule model only holds while the cell is confined (d < sphere diameter of V);
    # in a wider channel the cell is unconfined, so evaluate at the sphere diameter.
    d_sph = sphere_diameter(V)
    d_eff = min(d, d_sph)
    pr = passage(V, S, d_eff, stiffness_hypothesis=stiffness)
    cap = capsule_shape(V, d_eff)
    return {
        "sample_id": sample_id, "cell_id": cell_id,
        "channel_diameter": _T(d, "µm", "HYPOTHESIS", "chosen by the user"),
        "stiffness": _T(stiffness, "x normal", "HYPOTHESIS",
                        "carried along only; does not change the geometric verdict"),
        "volume": _T(V, "fL", "INFERRED"),
        "surface": _T(S, "µm²", "INFERRED"),
        "verdict": pr.verdict,
        "verdict_provenance": "COMPUTED",
        "mcd": _T(pr.mcd_um, "µm", "COMPUTED", "minimum cylindrical diameter, no stretch"),
        "mcd_at_lysis": _T(pr.mcd_at_lysis_um, "µm", "COMPUTED", "with 3 % area strain"),
        "surface_reserve": _T(pr.surface_reserve, "fraction", "COMPUTED", "S / S_required - 1"),
        "area_strain_needed": _T(pr.area_strain_needed, "fraction", "COMPUTED"),
        "caveat": pr.caveat,
        "unconfined": d >= d_sph,
        "capsule": {"radius_um": round(cap["radius_um"], 4),
                    "cylinder_length_um": round(cap["cylinder_length_um"], 4),
                    "total_length_um": round(cap["total_length_um"], 4),
                    "surface_um2": round(cap["surface_um2"], 4),
                    "provenance": "COMPUTED",
                    "note": "visualisation constrained by V; not a mechanical simulation"},
        "shape": x["extra"].get("shape"),
    }


@app.get("/api/samples/{sample_id}/cells/{cell_id}/stl")
def cell_stl(sample_id: str, cell_id: str):
    x = _cell(sample_id, _check_id(cell_id))
    sh = x["extra"]["shape"]
    m = mesh_cell(float(sh["morph_t"]), float(sh["radius_um"]))
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "cell.stl"
        write_stl(m, str(p), scale=STL_SCALE, name=f"{sample_id}_{cell_id}_x5000")
        data = p.read_bytes()
    fname = f"celllab_{sample_id}_{cell_id}_x5000.stl"
    return Response(content=data, media_type="model/stl",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


# ---------------------------------------------------------------------------
# routes: agent (delegates to backend.agent.orchestrator if present)
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    sample_ids: List[str]
    question: str = ""


_runs: Dict[str, Dict[str, Any]] = {}       # run_id -> {"status", "error"}


def _load_orchestrator():
    """Lazy import so the API starts even if the agent module is broken or missing."""
    try:
        mod = importlib.import_module("backend.agent.orchestrator")
    except Exception as e:                      # noqa: BLE001
        return None, f"backend.agent.orchestrator not importable: {e}"
    if callable(getattr(mod, "run_agent", None)) or callable(getattr(mod, "start_agent_run", None)):
        return mod, None
    return None, "backend.agent.orchestrator has neither run_agent() nor start_agent_run()"


def _run_in_thread(run_agent, run_id: str, req: RunRequest) -> None:
    """Same as orchestrator.start_agent_run, but our thread lets us report done/error."""
    try:
        _runs[run_id]["status"] = "running"
        run_agent(req.sample_ids, req.question, run_id=run_id)
        _runs[run_id]["status"] = "done"
    except Exception as e:                      # noqa: BLE001 (run_agent normally never raises)
        _runs[run_id].update(status="error", error=f"{type(e).__name__}: {e}"[:500])


@app.post("/api/agent/run")
def agent_run(req: RunRequest) -> Dict[str, str]:
    if not req.sample_ids:
        raise HTTPException(422, "sample_ids must not be empty")
    for sid in req.sample_ids:
        _sample_dir(sid)
    mod, err = _load_orchestrator()
    if mod is None:
        raise HTTPException(503, f"agent unavailable ({err}); use /api/replay/<name>")
    new_id = getattr(mod, "new_run_id", None)
    run_id = new_id() if callable(new_id) else (
        time.strftime("r%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6])
    (RUNS_DIR / run_id).mkdir(parents=True, exist_ok=True)   # /events answers immediately
    _runs[run_id] = {"status": "starting", "error": None}
    if callable(getattr(mod, "run_agent", None)):
        threading.Thread(target=_run_in_thread, args=(mod.run_agent, run_id, req),
                         daemon=True, name=f"celllab-api-{run_id}").start()
    else:
        mod.start_agent_run(req.sample_ids, req.question, run_id=run_id)
        _runs[run_id]["status"] = "running"
    return {"run_id": run_id}


def _read_jsonl(p: Path, after: int = 0) -> List[Dict]:
    out = []
    if not p.exists():
        return out
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue                            # partial last line while being written
        if int(ev.get("seq", 0)) > after:
            out.append(ev)
    return out


@app.get("/api/agent/run/{run_id}/events")
def agent_events(run_id: str, after: int = 0) -> Dict[str, Any]:
    """status: starting | running | done | error | unknown (run from a previous server)."""
    run_dir = RUNS_DIR / _check_id(run_id)
    if not run_dir.exists():
        raise HTTPException(404, f"unknown run: {run_id}")
    all_events = _read_jsonl(run_dir / "trace.jsonl", 0)
    events = [e for e in all_events if int(e.get("seq", 0)) > after]
    last = all_events[-1] if all_events else {}
    st = _runs.get(run_id, {"status": "unknown", "error": None})
    status, error = st["status"], st.get("error")
    if last.get("type") == "error":
        status, error = "error", error or last.get("text")
    elif status in ("unknown", "running", "starting") and (run_dir / "report.json").exists() \
            and last.get("type") == "report":
        status = "done" if status == "unknown" else status
    return {"run_id": run_id, "status": status, "error": error, "events": events}


@app.get("/api/replay/{name}")
def replay(name: str) -> Dict[str, Any]:
    name = _check_id(name.removesuffix(".jsonl"))
    p = DEMO_DIR / f"{name}.jsonl"
    if not p.exists():
        raise HTTPException(404, f"no replay named {name}")
    return {"name": name, "events": _read_jsonl(p)}
