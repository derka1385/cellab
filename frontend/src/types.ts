// Types mirroring docs/03_ARCHITECTURE_ET_CONTRATS.md section 4.
// Fields not in the contract are optional so the UI survives small backend variations.

export type Provenance = "MEASURED" | "CONSTRAINED" | "INFERRED" | "COMPUTED" | "HYPOTHESIS";

/** Tagged value (backend class `Tagged`). */
export interface Tagged {
  value: number | null;
  unit: string;
  provenance: Provenance;
  note?: string;
}

// 4.1 sample.json
export interface SampleCell {
  cell_id: string;
  centroid_px: [number, number];
  bbox_px: [number, number, number, number];
  contour_px: [number, number][];
  area: number;
  diameter: number;
  circularity: number;
  pallor_ratio: number;
  shape_class: string;
  shape_class_source: "annotation" | "classifier" | "none" | string;
  excluded: boolean;
  exclusion_reason: string | null;
}

export interface Sample {
  sample_id: string;
  label: string;
  image_path: string | null;
  pixel_size_um: number | null;
  source: string;
  note?: string;
  cells: SampleCell[];
}

// 4.2 cbc.json
export interface CBC {
  mcv_fl: number;
  rdw_cv_pct?: number | null;
  mchc_g_dl?: number | null;
  source: string;
  note?: string;
}

// 4.3 population.json
export interface PopulationCell {
  cell_id: string;
  shape_class: string;
  measured: {
    area_um2: Tagged;
    diameter_um: Tagged;
    circularity: Tagged;
    pallor_ratio: Tagged;
  };
  volume_fl: Tagged;
  sphericity_index: Tagged;
  surface_um2: Tagged;
  mcd_um: Tagged;
}

export type Verdict = "PASSES" | "PASSES_UNDER_STRAIN" | "BLOCKED";

export interface CellExtra {
  shape: { morph_t: number; radius_um: number; provenance: Provenance };
  passage_at_3um: { verdict: Verdict; area_strain_needed: number; mcd_um?: number; provenance: Provenance };
}

export interface Sweep {
  diameters_um: number[];
  passes: number[];
  passes_under_strain: number[];
  blocked: number[];
  provenance: Provenance;
}

export interface ConsistencyFlag {
  check: string;
  status: "COHERENT" | "INCOHERENT" | string;
  [k: string]: unknown;
}

export interface Population {
  sample_id: string;
  cells: PopulationCell[];
  cell_extra: Record<string, CellExtra>;
  sweep: Sweep;
  d50_um: number | null;
  d50?: Tagged;
  consistency: ConsistencyFlag[];
  synthetic: boolean;
  n_cells?: number;
  n_excluded?: number;
}

/** GET /api/samples row. */
export interface SampleSummary {
  sample_id: string;
  label: string;
  has_cbc?: boolean;
  has_image?: boolean;
  n_cells?: number;
  synthetic?: boolean;
  source?: string;
}

/** GET /api/samples/{id} */
export interface SampleBundle {
  sample: Sample;
  cbc: CBC | null;
  population: Population;
}

/** GET /api/samples/{id}/cells/{cell_id}/mesh (mesh_cell output). */
export interface CellMesh {
  vertices: [number, number, number][];
  faces: [number, number, number][];
  units?: string;
}

export interface Capsule {
  radius_um: number;
  cylinder_length_um: number;
  total_length_um: number;
  surface_um2?: number;
}

/** GET /api/samples/{id}/cells/{cell_id}/passage (passage() + capsule_shape()). */
export interface PassageResult {
  capillary_diameter_um: number;
  mcd_um: number;
  mcd_at_lysis_um: number;
  surface_reserve: number;
  area_strain_needed: number;
  verdict: Verdict;
  stiffness_hypothesis: number | null;
  caveat: string;
  provenance: Provenance;
  capsule: Capsule;
}

// 4.4 trace.jsonl
export interface TraceEvent {
  seq: number;
  t: number;
  type: "plan" | "tool_call" | "tool_result" | "message" | "report" | "error" | string;
  text?: string;
  id?: string;
  tool?: string;
  input?: Record<string, unknown>;
  output?: unknown;
  report_path?: string;
  report?: Report; // optional inline report (extension)
  [k: string]: unknown;
}

// 4.5 report.json
export interface ReportNumber {
  value: number;
  unit: string;
  provenance: Provenance;
  tool_call_id: string | null;
}

export interface Experiment {
  most_discriminating_width_um: number;
  suggested_constriction_widths_um: number[];
  predicted_pass_fraction: Record<string, Record<string, number>>;
  cells_per_sample_for_power: number | null;
  statistics: string;
  hypothesis: string;
  falsified_if: string;
  caveats: string[];
  provenance: Provenance;
}

export interface Report {
  title: string;
  summary: string;
  findings: { text: string; numbers: ReportNumber[] }[];
  consistency_flags: ConsistencyFlag[];
  experiment: Experiment | null;
  limitations: string[];
  number_guard: { checked: number; unverified: number };
}
