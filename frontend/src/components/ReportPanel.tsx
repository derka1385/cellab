import type { Experiment, Report } from "../types";
import { Num } from "./Num";
import { ProvenanceBadge } from "./ProvenanceBadge";

/** Render a finding's text with each declared number followed by its badge (in order). */
function FindingText({ text, numbers }: Report["findings"][number]) {
  // Badges are listed after the sentence, one per declared number, in declaration order.
  return (
    <li className="finding">
      <div>{text}</div>
      <div className="finding-nums">
        {numbers.map((n, i) => (
          <span key={i} className="finding-num" title={n.tool_call_id ? `from tool call ${n.tool_call_id}` : "declared hypothesis"}>
            <Num value={n.value} unit={n.unit} provenance={n.provenance} digits={n.unit === "fraction" ? 2 : 2} />
            {n.tool_call_id && <span className="tc">{n.tool_call_id}</span>}
          </span>
        ))}
      </div>
    </li>
  );
}

export function ReportPanel({ report, waiting }: { report: Report | null; waiting: string }) {
  if (!report) return <div className="report-empty muted">{waiting}</div>;
  const ng = report.number_guard;
  return (
    <div className="report">
      <div className="report-title">{report.title}</div>
      {ng && (
        <div className={`guard ${ng.unverified === 0 ? "guard-ok" : "guard-bad"}`}>
          number_guard: <Num value={ng.checked} provenance="COMPUTED" digits={0} /> numbers checked,{" "}
          <Num value={ng.unverified} provenance="COMPUTED" digits={0} /> invented
        </div>
      )}
      <p className="report-summary">{report.summary}</p>
      <ul className="findings">
        {report.findings.map((f, i) => (
          <FindingText key={i} {...f} />
        ))}
      </ul>
      {report.experiment && <ExperimentCard e={report.experiment} />}
      {report.limitations?.length > 0 && (
        <div className="limits">
          <b>Limitations</b>
          <ul>
            {report.limitations.map((l, i) => (
              <li key={i}>{l}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="disclaimer">Research hypothesis generator. Not a diagnosis.</div>
    </div>
  );
}

export function ExperimentCard({ e }: { e: Experiment }) {
  const widths = e.suggested_constriction_widths_um;
  const labels = Object.keys(e.predicted_pass_fraction[String(widths[0])] ?? Object.values(e.predicted_pass_fraction)[0] ?? {});
  const pred = (w: number) => e.predicted_pass_fraction[String(w)] ?? e.predicted_pass_fraction[w.toFixed(2)] ?? {};
  return (
    <div className="exp-card">
      <div className="exp-head">
        Proposed microfluidic experiment <ProvenanceBadge provenance={e.provenance ?? "COMPUTED"} />
      </div>
      <table className="exp-table">
        <thead>
          <tr>
            <th>Constriction</th>
            {labels.map((l, i) => (
              <th key={l} className={i === 0 ? "col-a" : "col-b"}>
                {i === 0 ? "A" : "B"} pass
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {widths.map((w) => (
            <tr key={w} className={w === e.most_discriminating_width_um ? "exp-best" : ""}>
              <td>
                <Num value={w} unit="µm" provenance="COMPUTED" />
              </td>
              {labels.map((l) => (
                <td key={l}>
                  <Num value={pred(w)[l]} unit="fraction" provenance="COMPUTED" />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="exp-n">
        Cells to count per sample <Num value={e.cells_per_sample_for_power} provenance="COMPUTED" digits={0} big />
        <span className="muted"> ({e.statistics})</span>
      </div>
      <div className="exp-hyp">
        <b>Hypothesis</b> {e.hypothesis}
      </div>
      <div className="exp-fals">
        <b>Falsified if</b> {e.falsified_if}
      </div>
    </div>
  );
}
