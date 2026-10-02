// Single data layer. Every component goes through `makeDataSource(mode)`; switching between
// mock files, the live API and replay is the `mode` value (see config.ts).
import type { DataMode } from "../config";
import { REPLAY_FILE } from "../config";
import type {
  CellMesh,
  PassageResult,
  Report,
  SampleBundle,
  SampleSummary,
  TraceEvent,
} from "../types";
import { capsuleShape, meshCell, meshToStl, passage as localPassage } from "./physics";

async function getJson<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText} for ${url}`);
  return (await res.json()) as T;
}

export function parseJsonl(text: string): TraceEvent[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map((l) => {
      try {
        return JSON.parse(l) as TraceEvent;
      } catch {
        return null;
      }
    })
    .filter((e): e is TraceEvent => e !== null)
    .sort((a, b) => a.seq - b.seq);
}

/** Accepts {sample, cbc, population} or a flat merge, so the API shape can vary slightly. */
function normaliseBundle(raw: any): SampleBundle {
  if (raw && raw.sample && raw.population) return { sample: raw.sample, cbc: raw.cbc ?? null, population: raw.population };
  throw new Error("Unexpected /api/samples/{id} payload: expected {sample, cbc, population}");
}

const untag = (x: any) => (x && typeof x === "object" && "value" in x ? x.value : x);

/** Accepts the raw passage() dict or the API's tagged variant (channel_diameter, mcd, ... as Tagged). */
function normalisePassage(raw: any, V: number | undefined, d: number): PassageResult {
  const src = raw.passage ?? raw;
  const r: any = {};
  for (const [k, v] of Object.entries(src)) r[k] = untag(v);
  r.capillary_diameter_um = r.capillary_diameter_um ?? r.channel_diameter ?? d;
  r.mcd_um = r.mcd_um ?? r.mcd;
  r.mcd_at_lysis_um = r.mcd_at_lysis_um ?? r.mcd_at_lysis;
  r.stiffness_hypothesis = r.stiffness_hypothesis ?? r.stiffness ?? null;
  r.provenance = r.verdict_provenance ?? r.provenance;
  if (src.capsule) r.capsule = src.capsule;
  if (!r.capsule) {
    if (raw.capsule) r.capsule = raw.capsule;
    else if (typeof raw.radius_um === "number") r.capsule = raw;
    else if (V !== undefined) r.capsule = capsuleShape(V, d);
  }
  r.provenance = r.provenance ?? "COMPUTED";
  r.caveat = r.caveat ?? "";
  return r as PassageResult;
}

function cellVS(bundle: SampleBundle, cellId: string) {
  const c = bundle.population.cells.find((x) => x.cell_id === cellId);
  if (!c) throw new Error(`cell ${cellId} not in population`);
  return { V: c.volume_fl.value as number, S: c.surface_um2.value as number };
}

export interface RunPoll {
  events: TraceEvent[];
  done: boolean;
}

export interface DataSource {
  mode: DataMode;
  listSamples(): Promise<SampleSummary[]>;
  getSample(id: string): Promise<SampleBundle>;
  imageUrl(id: string): string;
  getMesh(id: string, cellId: string, bundle: SampleBundle): Promise<CellMesh>;
  getPassage(id: string, cellId: string, d: number, stiffness: number, bundle: SampleBundle): Promise<PassageResult>;
  downloadStl(id: string, cellId: string, bundle: SampleBundle): Promise<void>;
  /** Agent: live run (POST + polling) or replay file. */
  traceIsLive: boolean;
  startRun(sampleIds: string[], question: string): Promise<string>;
  pollRun(runId: string, after: number): Promise<RunPoll>;
  loadReplay(): Promise<TraceEvent[]>;
  loadReport(reportEvent: TraceEvent, all: TraceEvent[]): Promise<Report | null>;
}

// ---------------------------------------------------------------- mock (static files)
const mock: Omit<DataSource, "mode" | "traceIsLive"> = {
  listSamples: () => getJson<SampleSummary[]>("/mocks/samples.json"),
  async getSample(id) {
    const base = `/mocks/samples/${id}`;
    const [sample, population] = await Promise.all([getJson<any>(`${base}/sample.json`), getJson<any>(`${base}/population.json`)]);
    const cbc = await getJson<any>(`${base}/cbc.json`).catch(() => null);
    return { sample, cbc, population };
  },
  imageUrl: (id) => `/mocks/samples/${id}/image.png`,
  async getMesh(id, cellId, bundle) {
    try {
      return await getJson<CellMesh>(`/mocks/samples/${id}/meshes/${cellId}.json`);
    } catch {
      const sh = bundle.population.cell_extra[cellId]?.shape;
      if (!sh) throw new Error(`no shape for ${cellId}`);
      return meshCell(sh.morph_t, sh.radius_um); // TS port of mesh_cell()
    }
  },
  async getPassage(_id, cellId, d, stiffness, bundle) {
    const { V, S } = cellVS(bundle, cellId);
    return localPassage(V, S, d, stiffness);
  },
  async downloadStl(id, cellId, bundle) {
    const mesh = await mock.getMesh(id, cellId, bundle);
    const blob = new Blob([meshToStl(mesh, 5, `${id}_${cellId}`)], { type: "model/stl" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `celllab_${id}_${cellId}_x5000.stl`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  },
  async startRun() {
    return "replay";
  },
  async pollRun() {
    return { events: [], done: true };
  },
  async loadReplay() {
    const res = await fetch(REPLAY_FILE);
    if (!res.ok) throw new Error(`replay file missing: ${REPLAY_FILE}`);
    return parseJsonl(await res.text());
  },
  async loadReport(ev, all) {
    if (ev.report) return ev.report;
    if (ev.report_path) {
      // "data/runs/<run>/report.json" -> "/mocks/runs/<run>/report.json"
      const rel = ev.report_path.replace(/^backend\//, "").replace(/^data\//, "");
      try {
        return await getJson<Report>(`/mocks/${rel}`);
      } catch {
        /* fall through */
      }
    }
    return reportFromSubmit(all);
  },
};

/** Contract-safe fallback: the agent passes the full report as input to submit_report (section 5). */
function reportFromSubmit(all: TraceEvent[]): Report | null {
  for (let i = all.length - 1; i >= 0; i--) {
    const e = all[i];
    if (e.type === "tool_call" && e.tool === "submit_report" && e.input) {
      const r = (e.input as any).report ?? e.input;
      if (r && r.title) return r as Report;
    }
  }
  return null;
}

// ---------------------------------------------------------------- live API
const api: Omit<DataSource, "mode" | "traceIsLive"> = {
  listSamples: async () => {
    const raw = await getJson<any>("/api/samples");
    return (Array.isArray(raw) ? raw : raw.samples ?? []).map((s: any) =>
      typeof s === "string" ? { sample_id: s, label: s } : s,
    );
  },
  getSample: async (id) => normaliseBundle(await getJson<any>(`/api/samples/${id}`)),
  imageUrl: (id) => `/api/samples/${id}/image`,
  getMesh: (id, cellId) => getJson<CellMesh>(`/api/samples/${id}/cells/${cellId}/mesh`),
  async getPassage(id, cellId, d, stiffness, bundle) {
    const raw = await getJson<any>(`/api/samples/${id}/cells/${cellId}/passage?d=${d.toFixed(3)}&stiffness=${stiffness}`);
    let V: number | undefined;
    try {
      V = cellVS(bundle, cellId).V;
    } catch {
      V = undefined;
    }
    return normalisePassage(raw, V, d);
  },
  async downloadStl(id, cellId) {
    const a = document.createElement("a");
    a.href = `/api/samples/${id}/cells/${cellId}/stl`;
    a.download = `celllab_${id}_${cellId}_x5000.stl`;
    a.click();
  },
  async startRun(sampleIds, question) {
    const r = await getJson<{ run_id: string }>("/api/agent/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ sample_ids: sampleIds, question }),
    });
    return r.run_id;
  },
  async pollRun(runId, after) {
    const raw = await getJson<any>(`/api/agent/run/${runId}/events?after=${after}`);
    const events: TraceEvent[] = Array.isArray(raw) ? raw : raw.events ?? [];
    const done =
      (!Array.isArray(raw) && (raw.done === true || ["done", "finished", "error", "failed"].includes(raw.status))) ||
      events.some((e) => e.type === "report" || e.type === "error");
    return { events, done };
  },
  loadReplay: mock.loadReplay, // always the bundled file: no network needed
  async loadReport(ev, all) {
    if (ev.report) return ev.report;
    return reportFromSubmit(all) ?? mock.loadReport(ev, all);
  },
};

/** API first, mock on failure (replay mode must survive a dead backend). */
function withFallback<K extends keyof typeof api>(k: K): (typeof api)[K] {
  return (async (...args: any[]) => {
    try {
      return await (api[k] as any)(...args);
    } catch (e) {
      console.warn(`[replay] API ${String(k)} failed, using mocks`, e);
      return (mock[k] as any)(...args);
    }
  }) as any;
}

export function makeDataSource(mode: DataMode): DataSource {
  if (mode === "mock") return { ...mock, mode, traceIsLive: false };
  if (mode === "live") return { ...api, mode, traceIsLive: true };
  return {
    mode,
    traceIsLive: false,
    listSamples: withFallback("listSamples"),
    getSample: withFallback("getSample"),
    imageUrl: api.imageUrl,
    getMesh: withFallback("getMesh"),
    getPassage: withFallback("getPassage"),
    downloadStl: withFallback("downloadStl"),
    startRun: mock.startRun,
    pollRun: mock.pollRun,
    loadReplay: mock.loadReplay,
    loadReport: mock.loadReport,
  };
}
