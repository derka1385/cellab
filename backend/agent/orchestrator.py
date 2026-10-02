"""
CellLab agent orchestrator: Messages API tool-use loop + trace.jsonl (contract 4.4)
+ report.json (contract 4.5).

Library use (from the API):
    from backend.agent.orchestrator import run_agent, start_agent_run
    run_id = run_agent(["synthetic_healthy", "synthetic_hs"], "Which sample fails 3 µm?")
    run_id = start_agent_run([...], "...")   # same, in a background thread; returns at once

CLI (from repo root):
    # live run with Claude (needs ANTHROPIC_API_KEY), recorded for offline replay
    python -m backend.agent.orchestrator --record demo/replay_main.jsonl \
        --samples synthetic_healthy synthetic_hs \
        --question "Would any subpopulation fail to pass narrow channels?"
    # scripted dry run (no network, no key): real tool outputs, scripted decisions
    python -m backend.agent.orchestrator --scripted --record demo/replay_main.jsonl

Environment:
    ANTHROPIC_API_KEY   API key (read by the anthropic SDK)
    CELLLAB_MODEL       model id, default claude-sonnet-5-5
    CELLLAB_EFFORT      output_config.effort (low|medium|high), default medium
    CELLLAB_THINKING    auto (default) | between_tools | adaptive | omit
    CELLLAB_FALLBACKS   1 to send the server-side refusal fallback (beta) on the request

Trace events (one JSON object per line):
    plan         first text of the agent              {"text"}
    message      later text / progress notes          {"text"}            (frontend type)
    tool_call    {"id", "tool", "input"}
    tool_result  {"id", "tool", "output", "is_error"}
    report       {"report_path", "report"}            (inline report: extension for replay)
    error        {"text"}                             (frontend type)
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from backend.agent.prompts import build_system_prompt, build_user_message
from backend.agent.tools import TOOL_SCHEMAS, ToolRunner

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
RUNS_DIR = BACKEND_DIR / "data" / "runs"

DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOOL_CALLS = 20
MAX_MODEL_TURNS = 14
MAX_TOKENS = 8000
WALL_CLOCK_LIMIT_S = 150.0
DEFAULT_QUESTION = ("Would any subpopulation fail to pass narrow channels? Explain in terms of "
                    "surface-to-volume geometry and propose a falsifiable microfluidic experiment.")


# ---------------------------------------------------------------------------
# trace writer
# ---------------------------------------------------------------------------

class TraceWriter:
    """Appends contract-4.4 events to trace.jsonl, flushed after every line."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.monotonic) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("", encoding="utf-8")
        self._clock = clock
        self._t0 = clock()
        self.seq = 0
        self._lock = threading.Lock()

    def emit(self, type_: str, **fields: Any) -> Dict:
        with self._lock:
            self.seq += 1
            ev = {"seq": self.seq, "t": round(self._clock() - self._t0, 2), "type": type_, **fields}
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
                f.flush()
            return ev


# ---------------------------------------------------------------------------
# client helpers (defensive against SDK / model differences)
# ---------------------------------------------------------------------------

def _make_client():
    import anthropic  # imported lazily so tests and replay never need a key
    return anthropic.Anthropic(max_retries=2, timeout=90.0)


def _request_kwargs(model: str) -> Dict[str, Any]:
    """Model-specific request options. Everything optional is dropped on a 400 (see _create)."""
    kw: Dict[str, Any] = {}
    thinking = os.environ.get("CELLLAB_THINKING", "auto")
    if thinking == "auto":
        # Sonnet 5.5: lowest thinking setting, short progress notes between tool calls.
        thinking = "between_tools" if model.startswith("claude-sonnet-5-5") else "omit"
    if thinking == "between_tools":
        kw["thinking"] = {"type": "between_tools"}
    elif thinking == "adaptive":
        kw["thinking"] = {"type": "adaptive"}
    effort = os.environ.get("CELLLAB_EFFORT", "medium")
    if effort and effort != "omit":
        kw["output_config"] = {"effort": effort}
    return kw


def _create(client, use_beta_fallback: bool, **kw):
    """messages.create with one retry stripping optional parameters on a 400."""
    def call(params):
        if use_beta_fallback:
            return client.beta.messages.create(betas=["server-side-fallback-2026-07-01"],
                                               fallbacks="default", **params)
        return client.messages.create(**params)
    try:
        return call(kw)
    except Exception as e:  # noqa: BLE001
        status = getattr(e, "status_code", None)
        optional = [k for k in ("thinking", "output_config") if k in kw]
        if status == 400 and (optional or use_beta_fallback):
            stripped = {k: v for k, v in kw.items() if k not in optional}
            return client.messages.create(**stripped)
        raise


def _get(block: Any, name: str, default: Any = None) -> Any:
    if isinstance(block, dict):
        return block.get(name, default)
    return getattr(block, name, default)


# ---------------------------------------------------------------------------
# main loop
# ---------------------------------------------------------------------------

def new_run_id() -> str:
    return time.strftime("r%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:4]


def run_agent(sample_ids: List[str], question: str, run_id: Optional[str] = None,
              record_path: Optional[str] = None, *, client: Any = None,
              model: Optional[str] = None, max_tool_calls: int = MAX_TOOL_CALLS,
              runs_dir: Optional[Path] = None, plan_prefix: str = "",
              mode: str = "live") -> str:
    """
    Run the CellLab agent on `sample_ids`. Writes <runs_dir>/<run_id>/trace.jsonl incrementally
    and report.json once a report passes number_guard. Returns run_id (also on failure: the
    trace then ends with an "error" event). `client` is injectable (tests / scripted runs).
    """
    run_id = run_id or new_run_id()
    runs_dir = Path(runs_dir) if runs_dir else RUNS_DIR
    run_dir = runs_dir / run_id
    trace = TraceWriter(run_dir / "trace.jsonl")
    model = model or os.environ.get("CELLLAB_MODEL", DEFAULT_MODEL)
    runner = ToolRunner()
    ok = False
    try:
        ok = _loop(sample_ids, question, run_dir, trace, runner, client, model,
                   max_tool_calls, plan_prefix, mode)
    except Exception as e:  # noqa: BLE001 - the trace must always end cleanly
        trace.emit("error", text=f"{type(e).__name__}: {e}"[:500])
    if record_path:
        rp = Path(record_path)
        if not rp.is_absolute():
            rp = REPO_ROOT / rp
        rp.parent.mkdir(parents=True, exist_ok=True)
        if ok:
            shutil.copyfile(run_dir / "trace.jsonl", rp)
        else:
            print(f"[celllab] run {run_id} did not produce an accepted report; "
                  f"{rp} not written (trace: {run_dir / 'trace.jsonl'})")
    return run_id


def _loop(sample_ids, question, run_dir, trace, runner, client, model, max_tool_calls,
          plan_prefix, mode) -> bool:
    if client is None:
        client = _make_client()
    use_fallback = os.environ.get("CELLLAB_FALLBACKS") == "1"
    system = build_system_prompt(max_tool_calls)
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": build_user_message(sample_ids, question)}]
    extra = _request_kwargs(model)
    n_calls = 0
    planned = False
    nudged = False
    t_start = time.monotonic()

    for _turn in range(MAX_MODEL_TURNS):
        if time.monotonic() - t_start > WALL_CLOCK_LIMIT_S:
            trace.emit("error", text=f"wall-clock limit {WALL_CLOCK_LIMIT_S:.0f} s reached")
            return False
        resp = _create(client, use_fallback, model=model, max_tokens=MAX_TOKENS, system=system,
                       tools=TOOL_SCHEMAS, messages=messages, **extra)
        content = list(_get(resp, "content", []) or [])
        stop = _get(resp, "stop_reason")

        tool_uses = []
        for b in content:
            btype = _get(b, "type")
            text = None
            if btype == "text":
                text = _get(b, "text")
            elif btype == "thinking":
                text = _get(b, "thinking")      # progress notes (between_tools / updates)
            if text and text.strip():
                if not planned:
                    trace.emit("plan", text=(plan_prefix + text.strip()), model=model, mode=mode)
                    planned = True
                else:
                    trace.emit("message", text=text.strip())
            if btype == "tool_use":
                tool_uses.append(b)
        # Pass the assistant turn back unchanged (thinking blocks included).
        messages.append({"role": "assistant", "content": content})

        if stop == "refusal":
            trace.emit("error", text="model refused the request (stop_reason=refusal)")
            return False
        if stop == "pause_turn":
            continue
        if stop == "max_tokens" and not tool_uses:
            trace.emit("error", text="model output hit max_tokens")
            return False

        if not tool_uses:
            # end_turn without an accepted report: one nudge, then give up
            if runner.accepted_report is None and not nudged and n_calls < max_tool_calls:
                nudged = True
                messages.append({"role": "user", "content":
                                 "Finish now: call design_experiment if not done, then "
                                 "submit_report."})
                continue
            if runner.accepted_report is None:
                trace.emit("error", text="agent stopped without an accepted report")
                return False
            break

        results = []
        for b in tool_uses:
            call_id, name, tin = _get(b, "id"), _get(b, "name"), _get(b, "input") or {}
            trace.emit("tool_call", id=call_id, tool=name, input=tin)
            if n_calls >= max_tool_calls:
                out, is_err = {"error": f"tool budget of {max_tool_calls} calls exhausted"}, True
            else:
                n_calls += 1
                out, is_err = runner.execute(name, tin, call_id)
            trace.emit("tool_result", id=call_id, tool=name, output=out, is_error=is_err)
            results.append({"type": "tool_result", "tool_use_id": call_id,
                            "content": json.dumps(out, ensure_ascii=False, default=str),
                            **({"is_error": True} if is_err else {})})

        if runner.accepted_report is not None:
            rp = run_dir / "report.json"
            rp.write_text(json.dumps(runner.accepted_report, ensure_ascii=False, indent=1),
                          encoding="utf-8")
            rel = rp.relative_to(BACKEND_DIR).as_posix() if rp.is_relative_to(BACKEND_DIR) \
                else rp.as_posix()
            trace.emit("report", report_path=rel, report=runner.accepted_report)
            return True
        if n_calls >= max_tool_calls:
            trace.emit("error", text=f"tool budget of {max_tool_calls} calls exhausted "
                                     "without an accepted report")
            return False
        messages.append({"role": "user", "content": results})

    if runner.accepted_report is None:
        trace.emit("error", text=f"no accepted report after {MAX_MODEL_TURNS} model turns")
        return False
    return True


def start_agent_run(sample_ids: List[str], question: str, run_id: Optional[str] = None,
                    record_path: Optional[str] = None, **kw: Any) -> str:
    """Start run_agent in a daemon thread and return the run_id immediately (for the API)."""
    run_id = run_id or new_run_id()
    th = threading.Thread(target=run_agent, args=(sample_ids, question, run_id, record_path),
                          kwargs=kw, daemon=True, name=f"celllab-agent-{run_id}")
    th.start()
    return run_id


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> None:
    ap = argparse.ArgumentParser(description="CellLab agent")
    ap.add_argument("--samples", nargs="+", default=["synthetic_healthy", "synthetic_hs"])
    ap.add_argument("--question", default=DEFAULT_QUESTION)
    ap.add_argument("--record", help="copy the trace to this path (e.g. demo/replay_main.jsonl)")
    ap.add_argument("--run-id")
    ap.add_argument("--model", help=f"default: $CELLLAB_MODEL or {DEFAULT_MODEL}")
    ap.add_argument("--scripted", action="store_true",
                    help="no network: scripted decisions, real tool outputs (dry run)")
    ap.add_argument("--with-refusal", action="store_true",
                    help="scripted only: first report contains an unverified number")
    ap.add_argument("--delay", type=float, default=1.2,
                    help="scripted only: simulated model latency per turn (s)")
    a = ap.parse_args(argv)

    kw: Dict[str, Any] = {}
    if a.scripted:
        from backend.agent.scripted import ScriptedClient, SCRIPTED_LABEL, demo_script
        if len(a.samples) != 2:
            ap.error("--scripted needs exactly 2 samples")
        kw = dict(client=ScriptedClient(demo_script(a.samples[0], a.samples[1],
                                                    with_refusal=a.with_refusal),
                                        delay_s=a.delay),
                  model="scripted", plan_prefix=SCRIPTED_LABEL + " ", mode="scripted")
    elif not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        print("[celllab] warning: ANTHROPIC_API_KEY is not set; the SDK may still find a "
              "profile, otherwise use --scripted.")
    t0 = time.monotonic()
    model = a.model or kw.pop("model", None)
    kw.pop("model", None)
    run_id = run_agent(a.samples, a.question, a.run_id, a.record, model=model, **kw)
    dt = time.monotonic() - t0
    run_dir = RUNS_DIR / run_id
    rep = run_dir / "report.json"
    print(f"run_id={run_id}  {dt:.1f} s  trace={run_dir / 'trace.jsonl'}")
    if rep.exists():
        r = json.loads(rep.read_text(encoding="utf-8"))
        print(f"report: {r.get('title')}")
        print(f"number_guard: {r.get('number_guard')}")
    else:
        lines = (run_dir / "trace.jsonl").read_text(encoding="utf-8").splitlines()
        print("no report; last event:", lines[-1] if lines else "<empty>")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
