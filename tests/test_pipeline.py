"""Pipeline + API tests. Run from repo root: python -m pytest -q tests/test_pipeline.py"""
import json
import math
import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.api.app import app
from backend.pipeline import SAMPLES_DIR, build_population, write_synthetic_samples

SYNTH = ["synthetic_healthy", "synthetic_hs"]
TAGGED_KEYS = {"value", "unit", "provenance", "note"}
PROVENANCES = {"MEASURED", "CONSTRAINED", "INFERRED", "COMPUTED", "HYPOTHESIS"}


@pytest.fixture(scope="session", autouse=True)
def synthetic_samples():
    if not all((SAMPLES_DIR / s / "population.json").exists() for s in SYNTH):
        write_synthetic_samples()


@pytest.fixture(scope="session")
def pops():
    return {s: build_population(s) for s in SYNTH}


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


def _is_tagged(x):
    return isinstance(x, dict) and TAGGED_KEYS <= set(x) and x["provenance"] in PROVENANCES


@pytest.mark.parametrize("sid", SYNTH)
def test_population_valid(pops, sid):
    p = pops[sid]
    for k in ("sample_id", "cells", "cell_extra", "sweep", "d50_um", "consistency", "synthetic"):
        assert k in p, k
    assert p["sample_id"] == sid and p["synthetic"] is True
    assert len(p["cells"]) == 300
    for c in p["cells"]:
        for k in ("volume_fl", "sphericity_index", "surface_um2", "mcd_um"):
            assert _is_tagged(c[k]), (c["cell_id"], k)
        for k, v in c["measured"].items():
            assert _is_tagged(v) and v["provenance"] == "MEASURED"
        assert c["measured"]["area_um2"]["unit"] == "px²"   # pixel_size_um is null
        ex = p["cell_extra"][c["cell_id"]]
        assert ex["shape"]["provenance"] == "INFERRED"
        assert ex["passage_at_3um"]["verdict"] in {"PASSES", "PASSES_UNDER_STRAIN", "BLOCKED"}
    sw = p["sweep"]
    assert sw["provenance"] == "COMPUTED"
    assert len(sw["diameters_um"]) == 121
    assert sw["diameters_um"][0] == 2.0 and sw["diameters_um"][-1] == 5.0
    for i in range(121):
        tot = sw["passes"][i] + sw["passes_under_strain"][i] + sw["blocked"][i]
        assert abs(tot - 1) < 1e-3
    assert 2.0 < p["d50_um"] < 5.0 and _is_tagged(p["d50"])
    # JSON-serialisable without NaN
    json.dumps(p, allow_nan=False)


@pytest.mark.parametrize("sid,mcv", [("synthetic_healthy", 90.0), ("synthetic_hs", 84.0)])
def test_mean_volume_equals_mcv(pops, sid, mcv):
    meanV = np.mean([c["volume_fl"]["value"] for c in pops[sid]["cells"]])
    assert abs(meanV - mcv) < 0.01


def test_d50_healthy_below_hs(pops):
    assert pops["synthetic_healthy"]["d50_um"] < pops["synthetic_hs"]["d50_um"]


def test_population_cached(pops):
    t = time.perf_counter()
    build_population("synthetic_hs")
    assert time.perf_counter() - t < 0.5   # read from disk, no recompute


# ----------------------------------------------------------------------------- API

def test_api_samples(client):
    r = client.get("/api/samples")
    assert r.status_code == 200
    ids = {s["sample_id"] for s in r.json()}
    assert set(SYNTH) <= ids
    r = client.get("/api/samples/synthetic_hs")
    assert r.status_code == 200
    assert set(r.json()) == {"sample", "cbc", "population"}
    assert client.get("/api/samples/nope").status_code == 404
    assert client.get("/api/samples/synthetic_hs/image").status_code == 404   # no image


def test_api_cell_routes(client):
    base = "/api/samples/synthetic_hs/cells/c000"
    r = client.get(f"{base}/mesh")
    assert r.status_code == 200 and len(r.json()["faces"]) > 100
    r = client.get(f"{base}/passage", params={"d": 3.0, "stiffness": 2})
    j = r.json()
    assert r.status_code == 200 and j["verdict"] in {"PASSES", "PASSES_UNDER_STRAIN", "BLOCKED"}
    assert j["stiffness"]["provenance"] == "HYPOTHESIS"
    assert client.get(f"{base}/passage", params={"d": 10}).json()["verdict"] == "PASSES"
    r = client.get(f"{base}/stl")
    assert r.status_code == 200 and r.content.startswith(b"solid ")
    xs = [float(l.split()[1]) for l in r.text.splitlines() if l.strip().startswith("vertex")]
    assert 25 < max(xs) - min(xs) < 60      # ~4 cm object (mm units)
    assert client.get("/api/samples/synthetic_hs/cells/zzz/passage").status_code == 404


def test_api_passage_fast(client):
    url = "/api/samples/synthetic_hs/cells/c010/passage"
    client.get(url, params={"d": 3.0})     # warm cache
    ts = []
    for i in range(50):
        t = time.perf_counter()
        assert client.get(url, params={"d": 2.0 + i * 0.05}).status_code == 200
        ts.append(time.perf_counter() - t)
    assert np.median(ts) < 0.05 and max(ts) < 0.1


def test_api_replay(client):
    for name in ("replay_main", "replay_guard"):
        if not (SAMPLES_DIR.parents[2] / "demo" / f"{name}.jsonl").exists():
            continue
        j = client.get(f"/api/replay/{name}").json()
        assert j["events"] and j["events"][0]["seq"] >= 1
    assert client.get("/api/replay/does_not_exist").status_code == 404
    assert client.get("/api/agent/run/does_not_exist/events").status_code == 404


def test_api_agent_run_without_key_ends_with_error(client, monkeypatch):
    import shutil
    from backend.api.app import RUNS_DIR
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    r = client.post("/api/agent/run", json={"sample_ids": ["synthetic_hs"], "question": "?"})
    if r.status_code == 503:
        pytest.skip("orchestrator not available")
    assert r.status_code == 200
    rid = r.json()["run_id"]
    try:
        for _ in range(100):
            j = client.get(f"/api/agent/run/{rid}/events").json()
            if j["status"] in ("error", "done"):
                break
            time.sleep(0.1)
        assert j["status"] == "error" and j["error"]
        assert j["events"] and j["events"][-1]["type"] == "error"
    finally:
        shutil.rmtree(RUNS_DIR / rid, ignore_errors=True)
    assert client.post("/api/agent/run", json={"sample_ids": ["nope"]}).status_code == 404


CHULA = ["chula_264", "chula_246", "chula_102"]   # normal, mixed, spherocyte-rich


@pytest.mark.skipif(not all((SAMPLES_DIR / s / "cbc.json").exists() for s in CHULA),
                    reason="Chula samples not present")
def test_chula_populations():
    d50s = []
    for s in CHULA:
        p = build_population(s)
        assert p["synthetic"] is False
        assert all(c["status"] == "COHERENT" for c in p["consistency"]), (s, p["consistency"])
        d50s.append(p["d50_um"])
    assert d50s[0] < d50s[1] < d50s[2]
