"""
Tests for the CellLab agent (no network, no API key needed).

    python -m pytest tests/test_agent.py -q
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.agent import number_guard as ng
from backend.agent.orchestrator import TraceWriter, run_agent, _request_kwargs
from backend.agent.scripted import SCRIPTED_LABEL, ScriptedClient, demo_script
from backend.agent.tools import (MAX_RESULT_CHARS, TOOL_NAMES, TOOL_SCHEMAS, ToolRunner,
                                 result_chars)

A, B = "synthetic_healthy", "synthetic_hs"
CONTRACT_TOOLS = ["list_samples", "measure_sample", "infer_geometry", "check_cbc_consistency",
                  "sweep_channels", "find_subpopulation", "simulate_cell",
                  "select_cells_for_display", "design_experiment", "submit_report"]
PROVENANCES = {"MEASURED", "CONSTRAINED", "INFERRED", "COMPUTED", "HYPOTHESIS"}


def _read_trace(path: Path):
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

def test_tool_schemas_match_contract():
    assert TOOL_NAMES == CONTRACT_TOOLS
    for t in TOOL_SCHEMAS:
        assert set(t) == {"name", "description", "input_schema"}
        assert t["input_schema"]["type"] == "object"
        json.dumps(t)


ALL_CALLS = [
    ("list_samples", {}),
    ("measure_sample", {"sample_id": A}), ("measure_sample", {"sample_id": B}),
    ("infer_geometry", {"sample_id": B, "si_threshold": 0.87}),
    ("check_cbc_consistency", {"sample_id": B}),
    ("sweep_channels", {"sample_ids": [A, B], "d_min": 2.0, "d_max": 5.0}),
    ("sweep_channels", {"sample_ids": [A, B, A], "d_min": 2.5, "d_max": 4.5}),
    ("find_subpopulation", {"sample_id": B, "si_threshold": 0.85}),
    ("find_subpopulation", {"sample_id": A, "si_threshold": 0.95}),
    ("simulate_cell", {"sample_id": B, "cell_id": "c000", "diameter_um": 3.0,
                       "stiffness_hypothesis": 2.0}),
    ("select_cells_for_display", {"sample_id": B, "strategy": "typical"}),
    ("select_cells_for_display", {"sample_id": B, "strategy": "worst"}),
    ("select_cells_for_display", {"sample_id": B, "strategy": "borderline", "diameter_um": 3.1}),
    ("design_experiment", {"sample_a": A, "sample_b": B}),
]


@pytest.mark.parametrize("name,inp", ALL_CALLS)
def test_tools_run_and_are_compact(name, inp):
    out, err = ToolRunner().execute(name, inp, "tc_x")
    assert not err, out
    assert result_chars(out) < MAX_RESULT_CHARS, (name, result_chars(out))


def test_tools_never_return_raw_cells():
    r = ToolRunner()
    for name, inp in ALL_CALLS:
        out, _ = r.execute(name, inp, f"id_{name}")
        assert "cells" not in out or len(out["cells"]) <= 3


def test_tool_errors_are_returned_not_raised():
    r = ToolRunner()
    for name, inp in [("measure_sample", {"sample_id": "nope"}),
                      ("sweep_channels", {"sample_ids": [A], "d_min": 4, "d_max": 3}),
                      ("simulate_cell", {"sample_id": A, "cell_id": "zzz", "diameter_um": 3}),
                      ("select_cells_for_display", {"sample_id": A, "strategy": "random"}),
                      ("infer_geometry", {"sample_id": A, "bogus": 1}),
                      ("no_such_tool", {})]:
        out, err = r.execute(name, inp, "tc")
        assert err and "error" in out


def test_hs_incoherent_flag_is_visible():
    out, _ = ToolRunner().execute("check_cbc_consistency", {"sample_id": B}, "tc")
    assert out["overall"] == "INCOHERENT"
    assert any(c["check"] == "RDW_vs_diameter_CV" and c["status"] == "INCOHERENT"
               for c in out["checks"])


# ---------------------------------------------------------------------------
# number_guard
# ---------------------------------------------------------------------------

POOL = {"tc_01": {"fraction": 0.3133, "d50_um": 3.164, "rdw_cv_pct": 17.5,
                  "hyp": "At 3.12 µm, A passes at 87% vs B at 43%",
                  "pred": {"3.37": {"A": 0.993}}}}


def _rep(*texts, numbers=()):
    return {"title": "t", "summary": " ".join(texts), "findings":
            [{"text": "x", "numbers": list(numbers)}], "limitations": []}


@pytest.mark.parametrize("text", ["31% of cells", "0.31 of cells", "31.3 %", "D50 3.16 µm",
                                  "D50 3.2 µm", "RDW 17.5%", "at 3.12 µm", "87%", "0.87",
                                  "width 3.37 µm", "99%", "c012 and tc_04 and 3D view"])
def test_guard_accepts_tool_numbers(text):
    g = ng.check_report(_rep(text), POOL)
    assert g["unverified"] == 0, g


@pytest.mark.parametrize("text", ["42% of cells", "MCD 3.03 ± 0.21 µm".replace("3.03", "3.9"),
                                  "149 µm²", "D50 3.5 µm"])
def test_guard_rejects_invented_numbers(text):
    g = ng.check_report(_rep(text), POOL)
    assert g["unverified"] >= 1, g


def test_guard_hypothesis_exemption():
    num = {"value": 0.85, "unit": "", "provenance": "HYPOTHESIS", "tool_call_id": None}
    assert ng.check_report(_rep("SI above 0.85"), POOL)["unverified"] == 1
    assert ng.check_report(_rep("SI above 0.85", numbers=[num]), POOL)["unverified"] == 0
    assert ng.check_report(_rep("stiffness 4.5x (HYPOTHESIS)"), POOL)["unverified"] == 0


def test_guard_checks_structured_numbers():
    bad = {"value": 0.77, "unit": "fraction", "provenance": "COMPUTED", "tool_call_id": "tc_01"}
    good = {"value": 0.3133, "unit": "fraction", "provenance": "COMPUTED", "tool_call_id": "tc_01"}
    assert ng.check_report(_rep("ok", numbers=[good]), POOL)["unverified"] == 0
    assert ng.check_report(_rep("ok", numbers=[bad]), POOL)["unverified"] == 1


def test_submit_report_refuses_then_accepts():
    r = ToolRunner()
    r.execute("infer_geometry", {"sample_id": B}, "tc_01")
    rep = _rep("SI p50 is 0.787 and 12345 cells")
    out, err = r.execute("submit_report", {"report": rep}, "tc_02")
    assert err and out["accepted"] is False and out["number_guard"]["unverified"] == 1
    assert out["unverified_numbers"][0]["value"] == "12345"
    out, err = r.execute("submit_report", {"report": _rep("SI p50 is 0.787")}, "tc_03")
    assert not err and out["accepted"] and r.accepted_report["number_guard"]["unverified"] == 0


# ---------------------------------------------------------------------------
# full loop with the scripted client
# ---------------------------------------------------------------------------

def test_full_scripted_run_matches_contracts(tmp_path):
    client = ScriptedClient(demo_script(A, B, with_refusal=True))
    t0 = time.monotonic()
    run_id = run_agent([A, B], "Would any subpopulation fail narrow channels?", "r_test",
                       str(tmp_path / "replay.jsonl"), client=client, model="scripted",
                       runs_dir=tmp_path / "runs", plan_prefix=SCRIPTED_LABEL + " ")
    assert time.monotonic() - t0 < 60
    assert run_id == "r_test"
    run_dir = tmp_path / "runs" / "r_test"
    ev = _read_trace(run_dir / "trace.jsonl")

    # contract 4.4
    assert [e["seq"] for e in ev] == list(range(1, len(ev) + 1))
    assert all(isinstance(e["t"], (int, float)) for e in ev)
    assert all(b["t"] >= a["t"] for a, b in zip(ev, ev[1:]))
    assert ev[0]["type"] == "plan" and ev[0]["text"].startswith(SCRIPTED_LABEL)
    assert ev[-1]["type"] == "report"
    assert {e["type"] for e in ev} <= {"plan", "message", "tool_call", "tool_result", "report"}
    calls = {e["id"]: e for e in ev if e["type"] == "tool_call"}
    results = [e for e in ev if e["type"] == "tool_result"]
    assert len(calls) == len(results) <= 20
    for r in results:
        assert r["id"] in calls and calls[r["id"]]["tool"] == r["tool"]
        assert r["seq"] > calls[r["id"]]["seq"]
    for c in calls.values():
        assert c["tool"] in CONTRACT_TOOLS and isinstance(c["input"], dict)

    # number_guard rejected then accepted
    subs = [r for r in results if r["tool"] == "submit_report"]
    assert len(subs) == 2
    assert subs[0]["is_error"] and subs[0]["output"]["accepted"] is False
    assert subs[0]["output"]["unverified_numbers"]
    assert subs[1]["output"]["accepted"] is True

    # non-trivial decisions: SI threshold and sweep window derived from earlier results
    sub_call = next(c for c in calls.values() if c["tool"] == "find_subpopulation")
    geo_a = next(r["output"] for r in results if r["tool"] == "infer_geometry"
                 and r["output"]["sample_id"] == A)
    assert geo_a["fraction_si_above"][f"{sub_call['input']['si_threshold']:g}"] <= 0.01
    sw = next(c for c in calls.values() if c["tool"] == "sweep_channels")
    assert (sw["input"]["d_min"], sw["input"]["d_max"]) != (2.0, 5.0)
    border = next(c for c in calls.values() if c["tool"] == "select_cells_for_display"
                  and c["input"]["strategy"] == "borderline")
    sw_res = next(r["output"] for r in results if r["tool"] == "sweep_channels")
    assert border["input"]["diameter_um"] == sw_res["max_gap"]["width_um"]

    # contract 4.5
    rep = json.loads((run_dir / "report.json").read_text(encoding="utf-8"))
    assert ev[-1]["report"] == rep
    assert ev[-1]["report_path"].endswith("r_test/report.json")
    assert set(rep) >= {"title", "summary", "findings", "consistency_flags", "experiment",
                        "limitations", "number_guard"}
    assert rep["number_guard"]["unverified"] == 0 and rep["number_guard"]["checked"] > 10
    for f in rep["findings"]:
        for n in f["numbers"]:
            assert n["provenance"] in PROVENANCES
            assert set(n) == {"value", "unit", "provenance", "tool_call_id"}
            assert (n["tool_call_id"] is None) == (n["provenance"] == "HYPOTHESIS")
            if n["tool_call_id"]:
                assert n["tool_call_id"] in calls
    assert any("pallor" in l for l in rep["limitations"])
    assert any(fl["status"] == "INCOHERENT" for fl in rep["consistency_flags"])
    assert "diagnos" not in json.dumps(rep).lower()

    # independent re-check of the accepted report against the trace's tool results
    pool = {r["id"]: r["output"] for r in results if not r["is_error"]
            and r["tool"] != "submit_report"}
    assert ng.check_report(rep, pool)["unverified"] == 0

    # recording
    assert (tmp_path / "replay.jsonl").read_text() == (run_dir / "trace.jsonl").read_text()


class _LoopingClient:
    """Fake model that never stops calling tools."""

    def __init__(self):
        self.n = 0
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.n += 1
        blocks = [SimpleNamespace(type="text", text=f"turn {self.n}")]
        blocks += [SimpleNamespace(type="tool_use", id=f"t{self.n}_{i}", name="list_samples",
                                   input={}) for i in range(3)]
        return SimpleNamespace(content=blocks, stop_reason="tool_use")


def test_tool_budget_is_enforced(tmp_path):
    run_agent([A, B], "q", "r_loop", client=_LoopingClient(), model="fake",
              runs_dir=tmp_path)
    ev = _read_trace(tmp_path / "r_loop" / "trace.jsonl")
    executed = [e for e in ev if e["type"] == "tool_result" and not e["is_error"]]
    assert len(executed) == 20
    assert ev[-1]["type"] == "error"
    assert not (tmp_path / "r_loop" / "report.json").exists()


def test_end_turn_without_report_nudges_then_errors(tmp_path):
    calls = []

    def create(**kw):
        calls.append(list(kw["messages"]))      # snapshot: the loop appends afterwards
        return SimpleNamespace(content=[SimpleNamespace(type="text", text="I am done.")],
                               stop_reason="end_turn")

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    run_agent([A, B], "q", "r_end", client=client, model="fake", runs_dir=tmp_path)
    ev = _read_trace(tmp_path / "r_end" / "trace.jsonl")
    assert len(calls) == 2 and "submit_report" in calls[1][-1]["content"]
    assert ev[0]["type"] == "plan" and ev[-1]["type"] == "error"


def test_exception_in_client_ends_trace_with_error(tmp_path):
    def create(**kw):
        raise RuntimeError("network down")
    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    run_agent([A], "q", "r_exc", client=client, model="fake", runs_dir=tmp_path)
    ev = _read_trace(tmp_path / "r_exc" / "trace.jsonl")
    assert ev[-1]["type"] == "error" and "network down" in ev[-1]["text"]


def test_400_on_optional_params_is_retried_without_them(tmp_path, monkeypatch):
    monkeypatch.setenv("CELLLAB_THINKING", "between_tools")
    seen = []
    script = ScriptedClient(demo_script(A, B))

    def create(**kw):
        seen.append(set(kw))
        if "thinking" in kw:
            err = Exception("thinking.type not supported")
            err.status_code = 400
            raise err
        return script.messages.create(**kw)

    client = SimpleNamespace(messages=SimpleNamespace(create=create))
    run_agent([A, B], "q", "r_400", client=client, model="claude-x", runs_dir=tmp_path)
    assert (tmp_path / "r_400" / "report.json").exists()
    assert "thinking" in seen[0] and "thinking" not in seen[1]


def test_request_kwargs_defaults(monkeypatch):
    monkeypatch.delenv("CELLLAB_THINKING", raising=False)
    monkeypatch.delenv("CELLLAB_EFFORT", raising=False)
    assert _request_kwargs("claude-sonnet-5-5")["thinking"] == {"type": "between_tools"}
    assert "thinking" not in _request_kwargs("claude-opus-5-5")
    assert _request_kwargs("claude-sonnet-5-5")["output_config"] == {"effort": "medium"}


def test_trace_writer_is_incremental(tmp_path):
    tw = TraceWriter(tmp_path / "t.jsonl")
    tw.emit("plan", text="a")
    assert len(_read_trace(tmp_path / "t.jsonl")) == 1
    tw.emit("tool_call", id="tc_01", tool="list_samples", input={})
    assert [e["seq"] for e in _read_trace(tmp_path / "t.jsonl")] == [1, 2]


def test_demo_replay_file_if_present():
    p = Path(__file__).resolve().parent.parent / "demo" / "replay_main.jsonl"
    if not p.exists():
        pytest.skip("demo/replay_main.jsonl not generated yet")
    ev = _read_trace(p)
    assert ev[0]["type"] == "plan" and ev[-1]["type"] == "report"
    assert ev[-1]["report"]["number_guard"]["unverified"] == 0
    if ev[0].get("mode") == "scripted":
        assert ev[0]["text"].startswith(SCRIPTED_LABEL)


def test_full_loop_through_real_sdk_with_mock_transport(tmp_path, monkeypatch):
    """Runs the loop through the installed anthropic SDK (HTTP mocked): catches SDK drift."""
    anthropic = pytest.importorskip("anthropic")
    try:                       # anthropic >= 1.0 uses httpx2, 0.x uses httpx
        import httpx2 as httpx
    except ImportError:
        httpx = pytest.importorskip("httpx")
    monkeypatch.delenv("CELLLAB_THINKING", raising=False)
    script = ScriptedClient(demo_script(A, B))
    bodies = []

    def handler(request):
        body = json.loads(request.content)
        bodies.append(body)
        resp = script.messages.create(**body)
        content = []
        for b in resp.content:
            if b.type == "text":
                content.append({"type": "text", "text": b.text})
            else:
                content.append({"type": "tool_use", "id": b.id, "name": b.name,
                                "input": b.input})
        return httpx.Response(200, json={
            "id": f"msg_{len(bodies)}", "type": "message", "role": "assistant",
            "model": body["model"], "content": content, "stop_reason": resp.stop_reason,
            "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 10}})

    client = anthropic.Anthropic(api_key="test-key",
                                 http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    run_agent([A, B], "q", "r_sdk", client=client, model="claude-sonnet-5-5", runs_dir=tmp_path)
    ev = _read_trace(tmp_path / "r_sdk" / "trace.jsonl")
    assert ev[-1]["type"] == "report", ev[-1]
    first = bodies[0]
    assert first["model"] == "claude-sonnet-5-5"
    assert first["thinking"] == {"type": "between_tools"}
    assert [t["name"] for t in first["tools"]] == CONTRACT_TOOLS
    # assistant turns are sent back as tool_use blocks, results as tool_result blocks
    later = bodies[2]["messages"]
    assert later[1]["role"] == "assistant"
    assert any(b["type"] == "tool_use" for b in later[1]["content"])
    assert all(b["type"] == "tool_result" for b in later[2]["content"])
