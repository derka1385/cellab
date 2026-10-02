import { useEffect, useRef } from "react";
import type { Provenance, TraceEvent } from "../types";
import type { TraceStatus } from "../hooks/useAgentTrace";
import { Num } from "./Num";

// Default provenance of a tool's numeric outputs (overridden by Tagged values in the output).
const TOOL_PROVENANCE: Record<string, Provenance> = {
  list_samples: "MEASURED",
  measure_sample: "MEASURED",
  infer_geometry: "INFERRED",
  check_cbc_consistency: "CONSTRAINED",
  find_subpopulation: "INFERRED",
  sweep_channels: "COMPUTED",
  simulate_cell: "COMPUTED",
  select_cells_for_display: "INFERRED",
  design_experiment: "COMPUTED",
  submit_report: "COMPUTED",
};

interface Props {
  events: TraceEvent[];
  status: TraceStatus;
  source: "live" | "replay" | null;
  error: string | null;
  onRun: () => void;
  onSkip: () => void;
  live: boolean;
}

export function AgentTrace({ events, status, source, error, onRun, onSkip, live }: Props) {
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    box.current?.scrollTo({ top: box.current.scrollHeight, behavior: "smooth" });
  }, [events.length]);
  const toolOf: Record<string, string> = {};
  for (const e of events) if (e.type === "tool_call" && e.id && e.tool) toolOf[e.id] = e.tool;

  return (
    <section className="panel trace-panel">
      <div className="panel-head">
        <span>
          Agent trace{" "}
          {source && <span className={`src src-${source}`}>{source === "live" ? "LIVE" : "REPLAY"}</span>}
          {status === "running" && <span className="pulse" />}
        </span>
        <span className="head-btns">
          {status === "running" && source === "replay" && (
            <button className="btn btn-sm" onClick={onSkip}>
              Skip
            </button>
          )}
          <button className="btn btn-sm btn-accent" onClick={onRun} title={live ? "Live run (L) · R = replay" : "Replay recorded run (R)"} disabled={status === "running"}>
            Run
          </button>
        </span>
      </div>
      <div className="trace" ref={box}>
        {events.length === 0 && status === "idle" && <div className="muted pad">Press “Run agent”: the agent plans, calls deterministic tools, then writes a report.</div>}
        {events.map((e) => (
          <TraceRow key={e.seq} e={e} tool={e.id ? toolOf[e.id] : undefined} />
        ))}
        {error && <div className="trace-error">{error}</div>}
      </div>
    </section>
  );
}

function TraceRow({ e, tool }: { e: TraceEvent; tool?: string }) {
  switch (e.type) {
    case "plan":
      return (
        <div className="ev ev-plan">
          <span className="ev-kind">PLAN</span>
          <span>{e.text}</span>
        </div>
      );
    case "message":
      return (
        <div className="ev ev-msg">
          <span className="ev-kind">THINK</span>
          <span>{e.text}</span>
        </div>
      );
    case "tool_call":
      return (
        <div className="ev ev-call">
          <span className="ev-kind">CALL</span>
          <span>
            <b className="tool">{e.tool}</b>
            <span className="args">({summariseInput(e.input)})</span>
          </span>
        </div>
      );
    case "tool_result":
      return (
        <div className="ev ev-result">
          <span className="ev-kind">RESULT</span>
          <ResultSummary output={e.output} provenance={TOOL_PROVENANCE[tool ?? ""] ?? "COMPUTED"} />
        </div>
      );
    case "report":
      return (
        <div className="ev ev-report">
          <span className="ev-kind">REPORT</span>
          <span>Report submitted and checked by number_guard → right panel</span>
        </div>
      );
    case "error":
      return (
        <div className="ev ev-err">
          <span className="ev-kind">ERROR</span>
          <span>{e.text ?? JSON.stringify(e)}</span>
        </div>
      );
    default:
      return (
        <div className="ev">
          <span className="ev-kind">{String(e.type).toUpperCase()}</span>
          <span>{e.text ?? ""}</span>
        </div>
      );
  }
}

function summariseInput(input?: Record<string, unknown>): string {
  if (!input) return "";
  return Object.entries(input)
    .filter(([k]) => k !== "report")
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join(", ")
    .slice(0, 90) || (input.report ? "report" : "");
}

interface Leaf {
  path: string;
  value: number | string | boolean;
  provenance?: Provenance;
  unit?: string;
}

/** Flatten the tool output to at most a handful of leaves, numbers keep a provenance badge. */
function flatten(o: unknown, prefix = "", out: Leaf[] = [], depth = 0): Leaf[] {
  if (out.length > 40 || depth > 3) return out;
  if (o && typeof o === "object" && !Array.isArray(o)) {
    const r = o as Record<string, unknown>;
    if ("value" in r && "provenance" in r && (typeof r.value === "number" || r.value === null)) {
      out.push({ path: prefix, value: r.value as number, provenance: r.provenance as Provenance, unit: r.unit as string });
      return out;
    }
    for (const [k, v] of Object.entries(r)) {
      if (["provenance", "caveats", "note", "falsified_if", "statistics", "hypothesis", "report"].includes(k)) continue;
      flatten(v, prefix ? `${prefix}.${k}` : k, out, depth + 1);
    }
  } else if (Array.isArray(o)) {
    if (o.every((x) => typeof x !== "object")) out.push({ path: prefix, value: o.slice(0, 4).join(", ") + (o.length > 4 ? "…" : "") });
    else out.push({ path: prefix, value: `${o.length} items` });
  } else if (typeof o === "number" || typeof o === "string" || typeof o === "boolean") {
    out.push({ path: prefix, value: o });
  }
  return out;
}

function ResultSummary({ output, provenance }: { output: unknown; provenance: Provenance }) {
  const leaves = flatten(output).slice(0, 5);
  return (
    <span className="result">
      {leaves.map((l, i) => (
        <span key={i} className="leaf">
          <span className="leaf-k">{l.path.split(".").slice(-2).join(".")}</span>{" "}
          {typeof l.value === "number" ? (
            <Num value={l.value} unit={l.unit ?? ""} provenance={l.provenance ?? provenance} digits={Number.isInteger(l.value) ? 0 : Math.abs(l.value) < 10 ? 3 : 1} />
          ) : (
            <span className="leaf-v">{String(l.value)}</span>
          )}
        </span>
      ))}
    </span>
  );
}
