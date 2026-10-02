"""
Scripted (offline) client for the CellLab agent loop.

`ScriptedClient` mimics `anthropic.Anthropic().messages.create`: each call returns the next
scripted assistant turn (text + tool_use blocks). Decisions in `demo_script` are computed
from the REAL tool results of the run (thresholds, sweep window, reference width), and the
report is assembled only from tool outputs, so it passes number_guard honestly.

This is NOT a Claude run. Every trace produced with it starts with SCRIPTED_LABEL.
Used by tests/test_agent.py and by `python -m backend.agent.orchestrator --scripted`.
"""
from __future__ import annotations

import json
import math
import time
from types import SimpleNamespace
from typing import Any, Callable, Dict, List, Optional, Tuple

SCRIPTED_LABEL = ("[scripted dry run, regenerate with a live key: decisions are scripted, "
                  "tool outputs are real]")


class Ctx:
    """What the scripted 'model' has seen so far: tool calls and their results."""

    def __init__(self) -> None:
        self.calls: Dict[str, Tuple[str, Dict]] = {}   # id -> (tool, input)
        self.results: Dict[str, Any] = {}              # id -> output
        self.errors: Dict[str, bool] = {}
        self._n = 0

    def new_id(self) -> str:
        self._n += 1
        return f"tc_{self._n:02d}"

    def find(self, tool: str, **match: Any) -> Tuple[str, Any]:
        """Most recent (id, output) of `tool` whose input contains `match`."""
        for cid in reversed(list(self.calls)):
            name, inp = self.calls[cid]
            if name == tool and all(inp.get(k) == v for k, v in match.items()) \
                    and cid in self.results:
                return cid, self.results[cid]
        raise KeyError(f"no result for {tool} {match}")


Step = Callable[[Ctx], Tuple[str, List[Tuple[str, Dict]]]]


def _block_text(text: str):
    return SimpleNamespace(type="text", text=text)


def _block_tool(cid: str, name: str, inp: Dict):
    return SimpleNamespace(type="tool_use", id=cid, name=name, input=inp)


class _Messages:
    def __init__(self, outer: "ScriptedClient") -> None:
        self._o = outer

    def create(self, **kw: Any):
        return self._o._next(kw)


class ScriptedClient:
    """Drop-in for anthropic.Anthropic() in run_agent(client=...)."""

    def __init__(self, steps: List[Step], delay_s: float = 0.0) -> None:
        self.steps = list(steps)
        self.delay_s = delay_s
        self.ctx = Ctx()
        self.messages = _Messages(self)
        self.requests: List[Dict] = []

    def _ingest(self, messages: List[Dict]) -> None:
        last = messages[-1] if messages else None
        if not last or last.get("role") != "user" or not isinstance(last.get("content"), list):
            return
        for b in last["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                self.ctx.results[b["tool_use_id"]] = json.loads(b["content"])
                self.ctx.errors[b["tool_use_id"]] = bool(b.get("is_error"))

    def _next(self, kw: Dict):
        self.requests.append({k: kw[k] for k in ("model", "system", "tools") if k in kw})
        self._ingest(kw.get("messages", []))
        if self.delay_s:
            time.sleep(self.delay_s)
        if not self.steps:
            return SimpleNamespace(content=[_block_text("Done.")], stop_reason="end_turn")
        text, calls = self.steps.pop(0)(self.ctx)
        blocks = [_block_text(text)] if text else []
        for name, inp in calls:
            cid = self.ctx.new_id()
            self.ctx.calls[cid] = (name, inp)
            blocks.append(_block_tool(cid, name, inp))
        return SimpleNamespace(content=blocks, stop_reason="tool_use" if calls else "end_turn")


# ---------------------------------------------------------------------------
# The demo script (sample A = reference, sample B = test)
# ---------------------------------------------------------------------------

def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def demo_script(A: str, B: str, with_refusal: bool = False) -> List[Step]:
    st: Dict[str, Any] = {}

    def s1(c: Ctx):
        return ("Plan: check image quality and CBC coherence for both samples, infer geometry, "
                "sweep channel widths over the observed MCD range, isolate the high-sphericity "
                "subpopulation, then design a falsifiable microfluidic test.",
                [("measure_sample", {"sample_id": A}), ("measure_sample", {"sample_id": B})])

    def s2(c: Ctx):
        _, ma = c.find("measure_sample", sample_id=A)
        _, mb = c.find("measure_sample", sample_id=B)
        return (f"Image data usable: {ma['n_kept']} cells kept in {A}, {mb['n_kept']} in {B}; "
                f"{_pct(mb['pallor_ratio']['fraction_below_0.1'])} of {B} cells show almost no "
                "central pallor. Next, CBC coherence.",
                [("check_cbc_consistency", {"sample_id": A}),
                 ("check_cbc_consistency", {"sample_id": B})])

    def s3(c: Ctx):
        notes = []
        for sid in (A, B):
            _, cc = c.find("check_cbc_consistency", sample_id=sid)
            for chk in cc["checks"]:
                if chk["status"] == "INCOHERENT":
                    if chk["check"] == "RDW_vs_diameter_CV":
                        notes.append(
                            f"{sid}: RDW_vs_diameter_CV is INCOHERENT (CBC RDW-CV "
                            f"{chk['rdw_cv_pct']}% vs {chk['implied_rdw_from_image_pct']}% "
                            "implied by the image).")
                    else:
                        notes.append(f"{sid}: {chk['check']} is INCOHERENT.")
        if notes:
            text = (" ".join(notes) + " I continue: volumes are anchored on the MCV, not on the "
                    "RDW, so the geometry stays usable, but the smear may under-represent the "
                    "size spread; the flag goes into the report. Now geometry.")
        else:
            text = "All CBC checks are COHERENT. Now geometry."
        return (text, [("infer_geometry", {"sample_id": A}), ("infer_geometry", {"sample_id": B})])

    def s4(c: Ctx):
        _, ga = c.find("infer_geometry", sample_id=A)
        _, gb = c.find("infer_geometry", sample_id=B)
        fa, fb = ga["fraction_si_above"], gb["fraction_si_above"]
        # Decision 1: lowest SI threshold where the reference sample is (almost) empty
        cands = sorted(fa, key=float)
        thr = next((k for k in cands if fa[k] <= 0.01 and fb[k] > fa[k]), cands[-1])
        st["thr"] = float(thr)
        # Decision 2: sweep window around the observed MCD range, not the default 2-5 µm
        lo = min(ga["mcd_um"]["p10"], gb["mcd_um"]["p10"])
        hi = max(ga["mcd_um"]["max"], gb["mcd_um"]["max"])
        d_min = round(math.floor((lo - 0.25) * 4) / 4, 2)
        d_max = round(math.ceil((hi + 0.1) * 4) / 4, 2)
        st["window"] = (d_min, d_max)
        text = (f"{A} has SI p90 {ga['sphericity_index']['p90']} and {_pct(fa[thr])} of cells "
                f"above SI {thr}, against {_pct(fb[thr])} in {B}: I isolate SI > {thr} as the "
                f"subpopulation threshold (HYPOTHESIS). MCD spans {lo} to {hi} µm, so I sweep "
                f"{d_min}-{d_max} µm rather than the default range.")
        return (text, [("find_subpopulation", {"sample_id": B, "si_threshold": float(thr)}),
                       ("sweep_channels", {"sample_ids": [A, B], "d_min": d_min,
                                           "d_max": d_max})])

    def s5(c: Ctx):
        _, sw = c.find("sweep_channels")
        gap = sw["max_gap"]
        st["w"] = gap["width_um"]
        return (f"The pass curves differ most at {gap['width_um']} µm ({_pct(gap[A])} of {A} vs "
                f"{_pct(gap[B])} of {B} pass without stretch); I use this width for the "
                "borderline cell. Picking cells for the 3D view.",
                [("select_cells_for_display", {"sample_id": A, "strategy": "typical"}),
                 ("select_cells_for_display", {"sample_id": B, "strategy": "worst"}),
                 ("select_cells_for_display", {"sample_id": B, "strategy": "borderline",
                                               "diameter_um": st["w"]})])

    def s6(c: Ctx):
        _, worst = c.find("select_cells_for_display", sample_id=B, strategy="worst")
        wc = worst["cells"][0]
        st["worst"] = wc["cell_id"]
        return (f"Worst cell {wc['cell_id']} has MCD {wc['mcd_um']} µm. I check it at "
                f"{st['w']} µm with a 2x stiffness HYPOTHESIS to show the geometric verdict does "
                "not depend on stiffness, then design the experiment.",
                [("simulate_cell", {"sample_id": B, "cell_id": wc["cell_id"],
                                    "diameter_um": st["w"], "stiffness_hypothesis": 2.0}),
                 ("design_experiment", {"sample_a": A, "sample_b": B})])

    def build_report(c: Ctx, bad: bool) -> Dict:
        id_ga, ga = c.find("infer_geometry", sample_id=A)
        id_gb, gb = c.find("infer_geometry", sample_id=B)
        id_sub, sub = c.find("find_subpopulation", sample_id=B)
        id_sw, sw = c.find("sweep_channels")
        id_sim, sim = c.find("simulate_cell")
        id_ex, ex = c.find("design_experiment")
        id_cb, cbb = c.find("check_cbc_consistency", sample_id=B)
        thr = st["thr"]
        thr_key = f"{thr:g}"
        fa = ga["fraction_si_above"].get(thr_key, 0.0)
        pa, pb = sw["per_sample"][A], sw["per_sample"][B]
        w = ex["most_discriminating_width_um"]
        pred = ex["predicted_pass_fraction"][f"{w:g}"]
        flags = [dict(chk, sample_id=B) for chk in cbb["checks"] if chk["status"] != "COHERENT"]
        p = sim["passage"]
        findings = [
            {"text": (f"{_pct(sub['fraction'])} of cells in {B} have a sphericity index above "
                      f"{thr} (INFERRED SI; threshold is a HYPOTHESIS), versus {_pct(fa)} in {A}."),
             "numbers": [
                 {"value": sub["fraction"], "unit": "fraction", "provenance": "COMPUTED",
                  "tool_call_id": id_sub},
                 {"value": thr, "unit": "", "provenance": "HYPOTHESIS", "tool_call_id": None},
                 {"value": fa, "unit": "fraction", "provenance": "COMPUTED",
                  "tool_call_id": id_ga}]},
            {"text": (f"This subpopulation has a median minimum cylindrical diameter of "
                      f"{sub['sub']['mcd_um_p50']} µm versus {sub['rest']['mcd_um_p50']} µm for "
                      f"the rest of {B} (COMPUTED): with less surface for its volume it cannot "
                      f"fold into a 3 µm capsule; {_pct(sub['sub']['blocked_at_3um'])} of it is "
                      "BLOCKED at 3 µm."),
             "numbers": [
                 {"value": sub["sub"]["mcd_um_p50"], "unit": "µm", "provenance": "COMPUTED",
                  "tool_call_id": id_sub},
                 {"value": sub["rest"]["mcd_um_p50"], "unit": "µm", "provenance": "COMPUTED",
                  "tool_call_id": id_sub},
                 {"value": sub["sub"]["blocked_at_3um"], "unit": "fraction",
                  "provenance": "COMPUTED", "tool_call_id": id_sub}]},
            {"text": (f"D50 (width where half the cells pass without stretch) is {pb['d50_um']} µm "
                      f"for {B} versus {pa['d50_um']} µm for {A} (COMPUTED). At {w} µm the model "
                      f"predicts {_pct(pred[A])} passage for {A} and {_pct(pred[B])} for {B}."),
             "numbers": [
                 {"value": pb["d50_um"], "unit": "µm", "provenance": "COMPUTED",
                  "tool_call_id": id_sw},
                 {"value": pa["d50_um"], "unit": "µm", "provenance": "COMPUTED",
                  "tool_call_id": id_sw},
                 {"value": pred[A], "unit": "fraction", "provenance": "COMPUTED",
                  "tool_call_id": id_ex},
                 {"value": pred[B], "unit": "fraction", "provenance": "COMPUTED",
                  "tool_call_id": id_ex}]},
            {"text": (f"Worst cell {sim['cell_id']} is {p['verdict']} at {p['capillary_diameter_um']}"
                      f" µm: it would need {_pct(p['area_strain_needed'])} area strain, beyond the "
                      f"{_pct(ga['model_constants']['lysis_area_strain'])} lysis limit (COMPUTED). "
                      "A 2x stiffness (HYPOTHESIS) cannot change a geometric BLOCKED verdict."),
             "numbers": [
                 {"value": p["area_strain_needed"], "unit": "fraction", "provenance": "COMPUTED",
                  "tool_call_id": id_sim},
                 {"value": ga["model_constants"]["lysis_area_strain"], "unit": "fraction",
                  "provenance": "COMPUTED", "tool_call_id": id_ga},
                 {"value": 2.0, "unit": "x normal", "provenance": "HYPOTHESIS",
                  "tool_call_id": None}]},
        ]
        for f in flags:
            if f["check"] == "RDW_vs_diameter_CV":
                findings.append({
                    "text": (f"CBC flag for {B}: RDW-CV {f['rdw_cv_pct']}% (CONSTRAINED) vs "
                             f"{f['implied_rdw_from_image_pct']}% implied by the image diameters "
                             "(MEASURED): the smear may under-represent the size spread; to be "
                             "confirmed on another field."),
                    "numbers": [
                        {"value": f["rdw_cv_pct"], "unit": "%", "provenance": "CONSTRAINED",
                         "tool_call_id": id_cb},
                        {"value": f["implied_rdw_from_image_pct"], "unit": "%",
                         "provenance": "MEASURED", "tool_call_id": id_cb}]})
        summary = (f"{B} contains a high-sphericity subpopulation ({_pct(sub['fraction'])} of "
                   f"cells) whose surface-to-volume ratio is too low to pass narrow channels; "
                   f"this is compatible with a spherocytic phenotype, to be confirmed. "
                   f"Proposed test: constrictions at {', '.join(str(x) for x in ex['suggested_constriction_widths_um'])}"
                   f" µm with {ex['cells_per_sample_for_power']} cells per sample.")
        if bad:
            summary += " Namvar et al. measured 149 µm² mean surface in healthy cells."
        return {
            "title": f"{B} shows a spherical subpopulation that fails {w} µm channels",
            "summary": summary,
            "findings": findings,
            "consistency_flags": flags,
            "experiment": ex,
            "limitations": [
                (f"Sphericity is inferred from central pallor (linear map: pallor ratio "
                 f"{ga['model_constants']['pallor_ratio_normal']} gives SI "
                 f"{ga['model_constants']['si_discocyte']}, no pallor gives SI "
                 f"{ga['model_constants']['si_spherocyte']}); validated only on annotated data."),
                "No mechanical simulation: capsule model in rigid cylindrical channels; stiffness "
                "is never predicted from images.",
                "Synthetic samples and demo CBC values, not patient data.",
            ],
        }

    def s7(c: Ctx):
        return ("Submitting the report.",
                [("submit_report", {"report": build_report(c, bad=with_refusal)})])

    def s8(c: Ctx):
        return ("number_guard refused one literature value that no tool produced; I remove it "
                "and resubmit.",
                [("submit_report", {"report": build_report(c, bad=False)})])

    steps: List[Step] = [s1, s2, s3, s4, s5, s6, s7]
    if with_refusal:
        steps.append(s8)
    return steps
