import type { Provenance } from "../types";

// Section 7: one colour per provenance, used everywhere. HYPOTHESIS has a dashed border.
export const PROVENANCE: Record<Provenance, { color: string; short: string; meaning: string }> = {
  MEASURED: { color: "#4ade80", short: "MEAS", meaning: "read on the image" },
  CONSTRAINED: { color: "#60a5fa", short: "CBC", meaning: "fixed by the blood count (CBC)" },
  INFERRED: { color: "#fbbf24", short: "INF", meaning: "model output" },
  COMPUTED: { color: "#a78bfa", short: "COMP", meaning: "deterministic physics" },
  HYPOTHESIS: { color: "#f472b6", short: "HYP", meaning: "chosen to explore a what-if" },
};

interface Props {
  provenance: Provenance | string;
  /** compact = short code (next to a number); full = whole word (legend, headers). */
  compact?: boolean;
  note?: string;
}

export function ProvenanceBadge({ provenance, compact = true, note }: Props) {
  const p = PROVENANCE[provenance as Provenance];
  if (!p) {
    // A value without a known provenance is a bug: make it visible.
    return (
      <span className="badge badge-unknown" title="Missing provenance: this is a bug">
        ??
      </span>
    );
  }
  const title = `${provenance}: ${p.meaning}${note ? ` — ${note}` : ""}`;
  return (
    <span
      className={`badge ${provenance === "HYPOTHESIS" ? "badge-hyp" : ""}`}
      style={{ color: p.color, borderColor: p.color, background: `${p.color}1f` }}
      title={title}
    >
      {compact ? p.short : provenance}
    </span>
  );
}

export function ProvenanceLegend() {
  return (
    <div className="legend">
      {(Object.keys(PROVENANCE) as Provenance[]).map((k) => (
        <ProvenanceBadge key={k} provenance={k} compact={false} />
      ))}
    </div>
  );
}
