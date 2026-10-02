import type { Provenance, Tagged } from "../types";
import { ProvenanceBadge } from "./ProvenanceBadge";

export function fmt(v: number | null | undefined, unit = "", digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  if (unit === "fraction" || unit === "%") return `${(v * (unit === "fraction" ? 100 : 1)).toFixed(digits === 2 ? 0 : digits)} %`;
  if (Number.isInteger(v) && digits === 0) return unit ? `${v} ${unit}` : String(v);
  const s = Math.abs(v) >= 100 ? v.toFixed(0) : v.toFixed(digits);
  return unit ? `${s} ${unit}` : s;
}

interface NumProps {
  value: number | null | undefined;
  unit?: string;
  provenance: Provenance | string;
  digits?: number;
  note?: string;
  big?: boolean;
}

/** Every number on screen goes through this component, so it always carries its provenance. */
export function Num({ value, unit = "", provenance, digits = 2, note, big }: NumProps) {
  return (
    <span className={`num ${big ? "num-big" : ""}`}>
      <span className="num-value">{fmt(value, unit, digits)}</span>
      <ProvenanceBadge provenance={provenance} note={note} />
    </span>
  );
}

export function TaggedNum({ t, digits = 2, big }: { t: Tagged | undefined; digits?: number; big?: boolean }) {
  if (!t) return <Num value={null} provenance="??" />;
  return <Num value={t.value} unit={t.unit} provenance={t.provenance} digits={digits} note={t.note} big={big} />;
}
