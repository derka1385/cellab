import { useCallback, useEffect, useRef, useState } from "react";
import { POLL_MS } from "../config";
import type { DataSource } from "../lib/dataSource";
import type { Report, TraceEvent } from "../types";

export type TraceStatus = "idle" | "running" | "done" | "error";

/**
 * Agent trace, event by event. Live mode polls /api/agent/run/{id}/events?after=<seq>;
 * replay mode reads the recorded JSONL and reveals events at their recorded pace.
 * Both feed the same `events` list, so the panel renders identically.
 */
export function useAgentTrace(ds: DataSource) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [status, setStatus] = useState<TraceStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [source, setSource] = useState<"live" | "replay" | null>(null);
  const gen = useRef(0); // invalidates any previous run/replay
  const pending = useRef<TraceEvent[]>([]); // replay events not yet shown (for skip)
  const allRef = useRef<TraceEvent[]>([]);

  const reset = useCallback(() => {
    gen.current++;
    pending.current = [];
    allRef.current = [];
    setEvents([]);
    setReport(null);
    setError(null);
    setStatus("idle");
  }, []);

  const append = useCallback(
    async (evs: TraceEvent[], g: number) => {
      if (g !== gen.current || evs.length === 0) return;
      const seen = new Set(allRef.current.map((e) => e.seq));
      const fresh = evs.filter((e) => !seen.has(e.seq));
      allRef.current = [...allRef.current, ...fresh].sort((a, b) => a.seq - b.seq);
      setEvents(allRef.current);
      const rep = fresh.find((e) => e.type === "report");
      if (rep) {
        const r = await ds.loadReport(rep, allRef.current).catch(() => null);
        if (g === gen.current) setReport(r);
      }
    },
    [ds],
  );

  const runReplay = useCallback(
    async (speed = 1) => {
      reset();
      const g = gen.current;
      setSource("replay");
      setStatus("running");
      try {
        const all = await ds.loadReplay();
        pending.current = [...all];
        let prevT = all[0]?.t ?? 0;
        for (const e of all) {
          if (g !== gen.current) return;
          const gap = Math.min(Math.max((e.t - prevT) / speed, 0.15), 1.6);
          prevT = e.t;
          await new Promise((r) => setTimeout(r, gap * 1000));
          if (g !== gen.current) return;
          pending.current = pending.current.filter((x) => x.seq !== e.seq);
          await append([e], g);
        }
        if (g === gen.current) setStatus("done");
      } catch (err) {
        if (g === gen.current) {
          setError(String(err));
          setStatus("error");
        }
      }
    },
    [ds, reset, append],
  );

  const runLive = useCallback(
    async (sampleIds: string[], question: string) => {
      reset();
      const g = gen.current;
      setSource("live");
      setStatus("running");
      try {
        const runId = await ds.startRun(sampleIds, question);
        let after = 0;
        for (;;) {
          if (g !== gen.current) return;
          const { events: evs, done } = await ds.pollRun(runId, after);
          await append(evs, g);
          if (evs.length) after = Math.max(after, ...evs.map((e) => e.seq));
          if (done) break;
          await new Promise((r) => setTimeout(r, POLL_MS));
        }
        if (g === gen.current) setStatus("done");
      } catch (err) {
        if (g === gen.current) {
          setError(`${err} — press R to replay the recorded run`);
          setStatus("error");
        }
      }
    },
    [ds, reset, append],
  );

  /** Replay only: show every remaining event now. */
  const skipToEnd = useCallback(async () => {
    const g = gen.current;
    const rest = pending.current;
    pending.current = [];
    gen.current++; // stop the timed loop
    const g2 = gen.current;
    void g;
    await append(rest, g2);
    setStatus("done");
  }, [append]);

  useEffect(() => () => void gen.current++, []);

  return { events, status, error, report, source, runLive, runReplay, skipToEnd, reset };
}
