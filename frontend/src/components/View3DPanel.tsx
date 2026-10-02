import type { PassageResult, PopulationCell } from "../types";
import { Num } from "./Num";
import { ProvenanceBadge } from "./ProvenanceBadge";
import { Scene3D, type ActorSpec } from "./Scene3D";

interface Props {
  actors: ActorSpec[];
  main: { sampleTag: "A" | "B"; cell: PopulationCell | null; passage: PassageResult | null; latencyMs: number | null };
  diameter: number;
  onDiameter: (d: number) => void;
  stiffness: number;
  onStiffness: (s: number) => void;
  durationS: number;
  playToken: number;
  onPlay: () => void;
  onReset: () => void;
  compare: boolean;
  onCompare: () => void;
  onStl: () => void;
  error: string | null;
}

const VERDICT_TEXT: Record<string, string> = {
  PASSES: "PASSES",
  PASSES_UNDER_STRAIN: "PASSES UNDER STRAIN",
  BLOCKED: "BLOCKED",
};

export function View3DPanel(p: Props) {
  const { cell, passage } = p.main;
  const strain = passage?.area_strain_needed ?? 0;
  return (
    <section className="panel view3d">
      <div className="view3d-head">
        <div className="h-title">
          Cell <b>{cell?.cell_id ?? "—"}</b>{" "}
          <span className={p.main.sampleTag === "A" ? "col-a" : "col-b"}>sample {p.main.sampleTag}</span>
        </div>
        {passage && (
          <div className={`verdict verdict-${passage.verdict}`}>
            {VERDICT_TEXT[passage.verdict] ?? passage.verdict} <ProvenanceBadge provenance={passage.provenance} />
          </div>
        )}
      </div>
      {cell && (
        <div className="cell-stats">
          <span>V <Num value={cell.volume_fl.value} unit="fL" provenance={cell.volume_fl.provenance} digits={1} /></span>
          <span>S <Num value={cell.surface_um2.value} unit="µm²" provenance={cell.surface_um2.provenance} digits={0} /></span>
          <span>SI <Num value={cell.sphericity_index.value} provenance={cell.sphericity_index.provenance} digits={2} /></span>
          <span>MCD <Num value={cell.mcd_um.value} unit="µm" provenance={cell.mcd_um.provenance} digits={2} /></span>
        </div>
      )}

      <div className="scene-wrap">
        <Scene3D actors={p.actors} diameter={p.diameter} playToken={p.playToken} durationS={p.durationS} />
        {p.error && <div className="scene-error">{p.error}</div>}
      </div>

      <div className="controls">
        <div className="strain-gauge" title="Membrane area strain needed to enter the channel (lysis limit ≈ 3 %)">
          <div className="sg-label">
            Area strain <Num value={strain * 100} unit="%" provenance="COMPUTED" digits={1} />
          </div>
          <div className="sg-bar">
            <div className="sg-fill" style={{ width: `${Math.min(strain / 0.03, 1) * 100}%` }} />
          </div>
          <div className="sg-scale">
            <span>0 %</span>
            {strain > 0.03 && <span className="sg-over">over lysis limit</span>}
            <span>3 %</span>
          </div>
        </div>
        <label className="slider">
          <span>
            Capillary D <Num value={p.diameter} unit="µm" provenance="HYPOTHESIS" digits={2} />
          </span>
          <input type="range" min={2} max={5} step={0.05} value={p.diameter} onChange={(e) => p.onDiameter(+e.target.value)} />
        </label>
        <label className="slider slider-hyp">
          <span>
            Stiffness <Num value={p.stiffness} unit="×" provenance="HYPOTHESIS" digits={1} />
          </span>
          <input type="range" min={1} max={5} step={0.5} value={p.stiffness} onChange={(e) => p.onStiffness(+e.target.value)} />
        </label>
        <button className="btn btn-accent btn-big" onClick={p.onPlay} disabled={!passage} title="Space">
          Simulate passage
        </button>
        <div className="buttons">
          <button className={`btn ${p.compare ? "btn-on" : ""}`} onClick={p.onCompare} title="C">
            Healthy vs test
          </button>
          <button className="btn" onClick={p.onReset}>
            Reset
          </button>
        </div>
        <button className="btn" onClick={p.onStl} disabled={!cell}>
          Download STL (×5000)
        </button>
      </div>
      <div className="caveat" title={p.main.latencyMs !== null ? `passage round-trip ${p.main.latencyMs.toFixed(0)} ms` : undefined}>
        {passage?.caveat
          ? passage.caveat
          : "Geometric visualisation (S, V conserved; no membrane mechanics). Stiffness changes speed only, never the verdict."}
      </div>
    </section>
  );
}
