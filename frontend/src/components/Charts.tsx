import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SampleBundle } from "../types";
import { Num } from "./Num";
import { ProvenanceBadge } from "./ProvenanceBadge";

export const COLOR_A = "#60a5fa";
export const COLOR_B = "#f87171";
const AXIS = { fill: "#c9d4e3", fontSize: 16 };
const TOOLTIP = { background: "#111827", border: "1px solid #334155", fontSize: 16 };

interface Props {
  a?: SampleBundle;
  b?: SampleBundle;
  diameter: number;
}

export function PassageChart({ a, b, diameter }: Props) {
  const data = useMemo(() => {
    const rows = new Map<number, { d: number; A?: number; B?: number }>();
    const add = (bd: SampleBundle | undefined, key: "A" | "B") => {
      if (!bd) return;
      const s = bd.population.sweep;
      s.diameters_um.forEach((d, i) => {
        const k = Math.round(d * 1000) / 1000;
        const r = rows.get(k) ?? { d: k };
        r[key] = Math.round(s.passes[i] * 1000) / 10;
        rows.set(k, r);
      });
    };
    add(a, "A");
    add(b, "B");
    return [...rows.values()].sort((x, y) => x.d - y.d);
  }, [a, b]);

  const d50 = (bd?: SampleBundle) => bd?.population.d50?.value ?? bd?.population.d50_um ?? null;

  return (
    <div className="chart-block">
      <div className="chart-title">
        Pass fraction (no strain) vs D <ProvenanceBadge provenance="COMPUTED" />
      </div>
      <div className="chart-sub">
        <span className="col-a">D50 A <Num value={d50(a)} unit="µm" provenance="COMPUTED" /></span>
        <span className="col-b">D50 B <Num value={d50(b)} unit="µm" provenance="COMPUTED" /></span>
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 6, right: 14, bottom: 2, left: -8 }}>
            <CartesianGrid stroke="#1f2937" />
            <XAxis dataKey="d" type="number" domain={[2, 5]} ticks={[2, 2.5, 3, 3.5, 4, 4.5, 5]} tick={AXIS} unit=" µm" height={26} />
            <YAxis domain={[0, 100]} ticks={[0, 50, 100]} tick={AXIS} unit="%" width={58} />
            <Tooltip contentStyle={TOOLTIP} formatter={(v: number) => `${v.toFixed(1)} % (COMPUTED)`} labelFormatter={(d) => `D = ${(+d).toFixed(2)} µm`} />
            <ReferenceLine x={diameter} stroke="#f472b6" strokeDasharray="6 4" strokeWidth={2} />
            <Line type="monotone" dataKey="A" name="A reference" stroke={COLOR_A} strokeWidth={3} dot={false} isAnimationActive={false} />
            <Line type="monotone" dataKey="B" name="B test" stroke={COLOR_B} strokeWidth={3} dot={false} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

export function SIHistogram({ a, b }: Omit<Props, "diameter">) {
  const data = useMemo(() => {
    const lo = 0.62, hi = 1.0, step = 0.02;
    const n = Math.round((hi - lo) / step);
    const rows = Array.from({ length: n }, (_, i) => ({ si: +(lo + (i + 0.5) * step).toFixed(2), A: 0, B: 0 }));
    const fill = (bd: SampleBundle | undefined, key: "A" | "B") => {
      if (!bd) return;
      const cells = bd.population.cells;
      for (const c of cells) {
        const v = c.sphericity_index.value ?? 0;
        const i = Math.min(n - 1, Math.max(0, Math.floor((v - lo) / step)));
        rows[i][key] += 100 / cells.length;
      }
    };
    fill(a, "A");
    fill(b, "B");
    return rows;
  }, [a, b]);
  return (
    <div className="chart-block">
      <div className="chart-title">
        Sphericity index distribution <ProvenanceBadge provenance="INFERRED" note="SI inferred from central pallor" />
      </div>
      <div style={{ flex: 1, minHeight: 0 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 4, right: 14, bottom: 2, left: -8 }} barGap={0} barCategoryGap={1}>
            <CartesianGrid stroke="#1f2937" vertical={false} />
            <XAxis dataKey="si" tick={AXIS} ticks={[0.66, 0.74, 0.82, 0.9, 0.98]} height={26} />
            <YAxis tick={AXIS} unit="%" width={58} allowDecimals={false} />
            <Tooltip contentStyle={TOOLTIP} formatter={(v: number) => `${v.toFixed(1)} % of cells (INFERRED)`} labelFormatter={(s) => `SI ≈ ${s}`} />
            <Legend wrapperStyle={{ fontSize: 16 }} />
            <Bar dataKey="A" name="A" fill={COLOR_A} fillOpacity={0.8} isAnimationActive={false} />
            <Bar dataKey="B" name="B" fill={COLOR_B} fillOpacity={0.8} isAnimationActive={false} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
