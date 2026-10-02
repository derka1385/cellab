import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { initialMode, initialSamples, type DataMode } from "./config";
import { makeDataSource } from "./lib/dataSource";
import type { CellMesh, PassageResult, SampleBundle } from "./types";
import { SamplePanel } from "./components/SamplePanel";
import { AgentTrace } from "./components/AgentTrace";
import { View3DPanel } from "./components/View3DPanel";
import { PassageChart, SIHistogram, COLOR_A, COLOR_B } from "./components/Charts";
import { ReportPanel } from "./components/ReportPanel";
import { ProvenanceLegend } from "./components/ProvenanceBadge";
import { useAgentTrace } from "./hooks/useAgentTrace";
import type { ActorSpec } from "./components/Scene3D";

const MODES: DataMode[] = ["mock", "live", "replay"];
const QUESTION =
  "Compare sample A and sample B: which cells would fail capillary passage, why, and what microfluidic experiment would test it?";

interface CellRef {
  sampleId: string;
  cellId: string;
}

/** Cell whose SI is at quantile q of its sample (q=0.5: typical, q=0.9: spherical tail). */
function cellAtQuantile(b: SampleBundle | undefined, q: number): string | null {
  if (!b || b.population.cells.length === 0) return null;
  const sorted = [...b.population.cells].sort((x, y) => (x.sphericity_index.value ?? 0) - (y.sphericity_index.value ?? 0));
  return sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))].cell_id;
}

const key = (c: CellRef) => `${c.sampleId}/${c.cellId}`;

export default function App() {
  const [mode, setMode] = useState<DataMode>(initialMode);
  const ds = useMemo(() => makeDataSource(mode), [mode]);
  const ids = useMemo(() => initialSamples(), []);
  const [bundles, setBundles] = useState<Record<string, SampleBundle | undefined>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [activeSample, setActiveSample] = useState(ids[1]);
  const [selection, setSelection] = useState<CellRef | null>(null);
  const [diameter, setDiameter] = useState(3.0);
  const [stiffness, setStiffness] = useState(1);
  const [compare, setCompare] = useState(false);
  const [playToken, setPlayToken] = useState(0);
  const [meshes, setMeshes] = useState<Record<string, CellMesh>>({});
  const [passages, setPassages] = useState<Record<string, PassageResult>>({});
  const [latency, setLatency] = useState<number | null>(null);
  const [viewError, setViewError] = useState<string | null>(null);
  const autoplay = useRef(false);
  const trace = useAgentTrace(ds);

  // ---- samples
  useEffect(() => {
    let alive = true;
    setLoadError(null);
    Promise.all(ids.map((id) => ds.getSample(id).then((b) => [id, b] as const)))
      .then((rows) => {
        if (!alive) return;
        setBundles(Object.fromEntries(rows));
        setMeshes({});
        setPassages({});
      })
      .catch((e) => alive && setLoadError(`Could not load samples (${mode} mode): ${e}`));
    return () => {
      alive = false;
    };
  }, [ds, ids, mode]);

  // default selection: a cell from the spherical tail of the test sample
  useEffect(() => {
    if (!selection && bundles[ids[1]]) {
      const c = cellAtQuantile(bundles[ids[1]], 0.9);
      if (c) setSelection({ sampleId: ids[1], cellId: c });
    }
  }, [bundles, ids, selection]);

  // ---- which cells are on stage
  const stage: CellRef[] = useMemo(() => {
    if (!selection) return [];
    if (!compare) return [selection];
    const a = selection.sampleId === ids[0] ? selection : { sampleId: ids[0], cellId: cellAtQuantile(bundles[ids[0]], 0.5) ?? "" };
    const b = selection.sampleId === ids[1] ? selection : { sampleId: ids[1], cellId: cellAtQuantile(bundles[ids[1]], 0.9) ?? "" };
    return [a, b].filter((c) => c.cellId);
  }, [selection, compare, ids, bundles]);

  // ---- meshes
  useEffect(() => {
    for (const c of stage) {
      const b = bundles[c.sampleId];
      if (!b || meshes[key(c)]) continue;
      ds.getMesh(c.sampleId, c.cellId, b)
        .then((m) => setMeshes((prev) => ({ ...prev, [key(c)]: m })))
        .catch((e) => setViewError(`mesh ${key(c)}: ${e}`));
    }
  }, [stage, bundles, ds, meshes]);

  // ---- passage (debounced: the slider fires on every move)
  useEffect(() => {
    if (stage.length === 0) return;
    const t = setTimeout(() => {
      const t0 = performance.now();
      Promise.all(
        stage.map(async (c) => {
          const b = bundles[c.sampleId];
          if (!b) return null;
          return [key(c), await ds.getPassage(c.sampleId, c.cellId, diameter, stiffness, b)] as const;
        }),
      )
        .then((rows) => {
          setLatency(performance.now() - t0);
          setViewError(null);
          setPassages((prev) => {
            const next = { ...prev };
            for (const r of rows) if (r) next[r[0]] = r[1];
            return next;
          });
        })
        .catch((e) => setViewError(`passage: ${e}`));
    }, 40);
    return () => clearTimeout(t);
  }, [stage, diameter, stiffness, bundles, ds]);

  const durationS = 4 * (1 + (stiffness - 1) * 0.5); // HYPOTHESIS slider: speed only

  const sameD = (p: PassageResult | undefined) => !!p && Math.abs(p.capillary_diameter_um - diameter) < 1e-3;

  const actors: ActorSpec[] = stage.map((c) => {
    const b = bundles[c.sampleId];
    const cell = b?.population.cells.find((x) => x.cell_id === c.cellId);
    const p = passages[key(c)];
    const isA = c.sampleId === ids[0];
    return {
      key: key(c),
      label: `${isA ? "A reference" : "B test"} · ${c.cellId}`,
      labelColor: isA ? COLOR_A : COLOR_B,
      mesh: meshes[key(c)] ?? null,
      volume: cell?.volume_fl.value ?? null,
      passage: sameD(p) ? p : null, // only animate against a verdict computed for the current D
    };
  });

  const mainRef = selection;
  const mainBundle = mainRef ? bundles[mainRef.sampleId] : undefined;
  const mainCell = mainBundle?.population.cells.find((x) => x.cell_id === mainRef?.cellId) ?? null;
  const mainPassage = mainRef ? passages[key(mainRef)] ?? null : null;
  const mainReady = !!mainRef && sameD(mainPassage ?? undefined) && !!meshes[key(mainRef)];

  // autoplay requested by the agent trace (simulate_cell) once the verdict for that D is in
  useEffect(() => {
    if (autoplay.current && mainReady) {
      autoplay.current = false;
      setPlayToken(Date.now());
    }
  }, [mainReady]);

  // ---- agent drives the 3D view: simulate_cell -> load that cell, set D, play
  const lastDriven = useRef(0);
  useEffect(() => {
    if (trace.events.length === 0) {
      lastDriven.current = 0;
      return;
    }
    const e = [...trace.events].reverse().find((x) => x.type === "tool_call" && x.tool === "simulate_cell");
    if (!e || e.seq <= lastDriven.current) return;
    lastDriven.current = e.seq;
    const inp = (e.input ?? {}) as { sample_id?: string; cell_id?: string; diameter_um?: number };
    if (inp.sample_id && inp.cell_id && bundles[inp.sample_id]) {
      setActiveSample(inp.sample_id);
      setSelection({ sampleId: inp.sample_id, cellId: inp.cell_id });
      if (typeof inp.diameter_um === "number") setDiameter(Math.min(5, Math.max(2, inp.diameter_um)));
      setPlayToken(0);
      autoplay.current = true;
    }
  }, [trace.events, bundles]);

  const play = useCallback(() => setPlayToken(Date.now()), []);
  const runAgent = useCallback(() => {
    if (ds.traceIsLive) void trace.runLive(ids, QUESTION);
    else void trace.runReplay();
  }, [ds, trace, ids]);

  // ---- keyboard: R replay, L live run, Space simulate, C compare, S skip, Shift+M cycle data mode
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      const t = ev.target as HTMLElement | null;
      if (t && (t.tagName === "TEXTAREA" || (t.tagName === "INPUT" && (t as HTMLInputElement).type !== "range"))) return;
      const k = ev.key.toLowerCase();
      if (k === "r") void trace.runReplay();
      else if (k === "l" && ds.traceIsLive) void trace.runLive(ids, QUESTION);
      else if (k === " ") {
        ev.preventDefault();
        play();
      } else if (k === "c") setCompare((x) => !x);
      else if (k === "m" && ev.shiftKey) setMode((m) => MODES[(MODES.indexOf(m) + 1) % MODES.length]);
      else if (k === "s" && trace.status === "running") void trace.skipToEnd();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [trace, ds, ids, play]);

  const anySynthetic = ids.some((id) => bundles[id]?.population.synthetic);
  const cycleMode = () => setMode((m) => MODES[(MODES.indexOf(m) + 1) % MODES.length]);

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="logo" title="Double-click (or Shift+M) cycles the data source" onDoubleClick={cycleMode}>
            CellLab
          </span>
          <span className="tagline">Run experiments on cells before touching the cells.</span>
        </div>
        <ProvenanceLegend />
        <div className="topbar-right">
          {anySynthetic && <span className="tag-synth">SYNTHETIC DEMO DATA</span>}
          <span className={`mode mode-${mode}`} title="Data source: mock files / live API / replay file">
            {mode.toUpperCase()}
          </span>
        </div>
      </header>
      {loadError && <div className="banner-error">{loadError}</div>}
      <main className="grid">
        <div className="col col-left">
          <SamplePanel
            ids={ids}
            bundles={bundles}
            active={activeSample}
            onActive={setActiveSample}
            selectedCell={selection?.sampleId === activeSample ? selection.cellId : null}
            onSelectCell={(sampleId, cellId) => {
              setSelection({ sampleId, cellId });
              setPlayToken(0);
              autoplay.current = true; // click -> 3D -> animated passage
            }}
            imageUrl={ds.imageUrl}
          />
          <AgentTrace
            events={trace.events}
            status={trace.status}
            source={trace.source}
            error={trace.error}
            live={ds.traceIsLive}
            onRun={runAgent}
            onSkip={() => void trace.skipToEnd()}
          />
        </div>
        <div className="col col-center">
          <View3DPanel
            actors={actors}
            main={{
              sampleTag: mainRef?.sampleId === ids[0] ? "A" : "B",
              cell: mainCell,
              passage: mainPassage,
              latencyMs: latency,
            }}
            diameter={diameter}
            onDiameter={setDiameter}
            stiffness={stiffness}
            onStiffness={setStiffness}
            durationS={durationS}
            playToken={playToken}
            onPlay={play}
            onReset={() => setPlayToken(0)}
            compare={compare}
            onCompare={() => setCompare((x) => !x)}
            onStl={() => mainRef && mainBundle && void ds.downloadStl(mainRef.sampleId, mainRef.cellId, mainBundle)}
            error={viewError}
          />
        </div>
        <div className="col col-right">
          <section className="panel charts">
            <PassageChart a={bundles[ids[0]]} b={bundles[ids[1]]} diameter={diameter} />
            <SIHistogram a={bundles[ids[0]]} b={bundles[ids[1]]} />
          </section>
          <section className="panel report-panel">
            <div className="panel-head">Agent report</div>
            <ReportPanel
              report={trace.report}
              waiting={trace.status === "running" ? "The agent is working…" : "No report yet. Run the agent (or press R to replay the recorded run)."}
            />
          </section>
        </div>
      </main>
    </div>
  );
}
