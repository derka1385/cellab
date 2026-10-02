import { useMemo, useRef, useState } from "react";
import type { SampleBundle } from "../types";
import { Num } from "./Num";

interface Props {
  ids: [string, string];
  bundles: Record<string, SampleBundle | undefined>;
  active: string;
  onActive: (id: string) => void;
  selectedCell: string | null;
  onSelectCell: (sampleId: string, cellId: string) => void;
  imageUrl: (id: string) => string;
}

/** SI -> colour: 0.72 (discocyte) green ... 0.92 (spherocyte) red. */
export function siColor(si: number): string {
  const t = Math.min(Math.max((si - 0.72) / 0.2, 0), 1);
  return `hsl(${Math.round(130 * (1 - t))} 80% 55%)`;
}

export function SamplePanel({ ids, bundles, active, onActive, selectedCell, onSelectCell, imageUrl }: Props) {
  const b = bundles[active];
  return (
    <section className="panel sample-panel">
      <div className="tabs">
        {ids.map((id, i) => (
          <button key={id} className={`tab ${id === active ? "tab-on" : ""} ${i === 0 ? "tab-a" : "tab-b"}`} onClick={() => onActive(id)}>
            {i === 0 ? "A" : "B"} · {i === 0 ? "reference" : "test"}
          </button>
        ))}
      </div>
      {!b ? (
        <div className="muted pad">Loading sample…</div>
      ) : (
        <>
          <div className="sample-label" title={b.sample.label}>
            <span>
              <Num value={b.population.cells.length} unit="cells" provenance="MEASURED" digits={0} /> {b.sample.label}
            </span>
            {(b.population.synthetic || b.sample.source === "synthetic") && <span className="tag-synth">SYNTHETIC</span>}
          </div>
          <Smear bundle={b} selectedCell={selectedCell} onSelect={(c) => onSelectCell(active, c)} imageUrl={imageUrl(active)} />
          <CbcBlock bundle={b} />
        </>
      )}
    </section>
  );
}

function Smear({ bundle, selectedCell, onSelect, imageUrl }: { bundle: SampleBundle; selectedCell: string | null; onSelect: (c: string) => void; imageUrl: string }) {
  const { sample, population } = bundle;
  const [imgFailed, setImgFailed] = useState(false);
  const hasImage = !!sample.image_path && !imgFailed;
  const siById = useMemo(() => {
    const m: Record<string, number> = {};
    for (const c of population.cells) m[c.cell_id] = c.sphericity_index.value ?? 0.74;
    return m;
  }, [population]);
  const full = useMemo(() => {
    let maxX = 0, maxY = 0;
    for (const c of sample.cells) {
      maxX = Math.max(maxX, c.bbox_px[0] + c.bbox_px[2]);
      maxY = Math.max(maxY, c.bbox_px[1] + c.bbox_px[3]);
    }
    return { x: 0, y: 0, w: maxX + 10, h: maxY + 10 };
  }, [sample]);
  const [view, setView] = useState(full);
  const [prevFull, setPrevFull] = useState(full);
  if (prevFull !== full) {
    setPrevFull(full);
    setView(full);
  }
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<{ x: number; y: number; moved: boolean } | null>(null);

  const onWheel = (e: React.WheelEvent) => {
    const svg = svgRef.current;
    if (!svg) return;
    const r = svg.getBoundingClientRect();
    const fx = (e.clientX - r.left) / r.width;
    const fy = (e.clientY - r.top) / r.height;
    const k = e.deltaY > 0 ? 1.15 : 1 / 1.15;
    const w = Math.min(full.w, Math.max(full.w / 10, view.w * k));
    const h = (w / view.w) * view.h;
    setView({ x: view.x + fx * (view.w - w), y: view.y + fy * (view.h - h), w, h });
  };
  const onDown = (e: React.PointerEvent) => (drag.current = { x: e.clientX, y: e.clientY, moved: false });
  const onMove = (e: React.PointerEvent) => {
    const d = drag.current;
    const svg = svgRef.current;
    if (!d || !svg) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true;
    if (!d.moved) return;
    const r = svg.getBoundingClientRect();
    setView((v) => ({ ...v, x: v.x - (dx * v.w) / r.width, y: v.y - (dy * v.h) / r.height }));
    drag.current = { x: e.clientX, y: e.clientY, moved: true };
  };
  const onUp = () => setTimeout(() => (drag.current = null), 0);

  return (
    <div className="smear">
      <svg
        ref={svgRef}
        viewBox={`${view.x} ${view.y} ${view.w} ${view.h}`}
        preserveAspectRatio="xMidYMid meet"
        onWheel={onWheel}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerLeave={onUp}
        onDoubleClick={() => setView(full)}
      >
        <rect x={full.x - 1000} y={full.y - 1000} width={full.w + 2000} height={full.h + 2000} fill={hasImage ? "#000" : "#f3e3e6"} />
        {hasImage && <image href={imageUrl} x={0} y={0} onError={() => setImgFailed(true)} />}
        {sample.cells.map((c) => {
          const si = siById[c.cell_id];
          const pts = c.contour_px.map((p) => p.join(",")).join(" ");
          const sel = c.cell_id === selectedCell;
          const col = c.excluded ? "#888" : siColor(si ?? 0.74);
          const r = c.diameter / 2;
          return (
            <g
              key={c.cell_id}
              className="smear-cell"
              onClick={() => !c.excluded && !drag.current?.moved && onSelect(c.cell_id)}
            >
              {!hasImage && (
                <>
                  <polygon points={pts} fill="#d9707d" />
                  {c.pallor_ratio > 0.02 && <circle cx={c.centroid_px[0]} cy={c.centroid_px[1]} r={r * c.pallor_ratio} fill="#f1c7cc" />}
                </>
              )}
              <polygon
                points={pts}
                fill={hasImage ? "transparent" : "none"}
                stroke={sel ? "#ffffff" : col}
                strokeWidth={sel ? 6 : 3}
                strokeDasharray={c.excluded ? "6 4" : undefined}
                vectorEffect="non-scaling-stroke"
              />
            </g>
          );
        })}
      </svg>
      <div className="smear-hint">
        {hasImage ? "Contours" : "Drawn from measurements"} · colour = SI · click
      </div>
    </div>
  );
}

function CbcBlock({ bundle }: { bundle: SampleBundle }) {
  const { cbc, population } = bundle;
  return (
    <div className="cbc">
      <div className="cbc-head">
        CBC {cbc && <span className="tag-demo">{cbc.source === "demo" ? "DEMO VALUES" : cbc.source}</span>}
      </div>
      {cbc ? (
        <div className="cbc-grid">
          <span>MCV</span>
          <Num value={cbc.mcv_fl} unit="fL" provenance="CONSTRAINED" digits={1} />
          <span>RDW</span>
          <Num value={cbc.rdw_cv_pct} unit="%" provenance="CONSTRAINED" digits={1} />
          <span>MCHC</span>
          <Num value={cbc.mchc_g_dl} unit="g/dL" provenance="CONSTRAINED" digits={1} />
        </div>
      ) : (
        <div className="muted">No CBC for this sample</div>
      )}
      <div className="flags">
        {population.consistency.map((f) => (
          <span key={f.check} className={`flag ${f.status === "COHERENT" ? "flag-ok" : "flag-bad"}`} title={JSON.stringify(f)}>
            {f.check.split("_")[0]}: {f.status === "COHERENT" ? "coherent" : "INCOHERENT"}
          </span>
        ))}
      </div>
    </div>
  );
}
