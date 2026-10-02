// Small TypeScript port of backend/physics/celllab_physics.py, used ONLY:
//  - in mock mode, to answer /passage and /mesh without the API (same formulas, COMPUTED/INFERRED),
//  - to build the capsule target shape with the same topology as the cell mesh (animation).
// The Python module stays the source of truth; keep formulas in sync if it changes.
import type { Capsule, CellMesh, PassageResult, Verdict } from "../types";

export const LYSIS_AREA_STRAIN = 0.03;
const EF_R0 = 3.91;
const EF_C0 = 0.81;
const EF_C2 = 7.83;
const EF_C4 = -4.39;

export const sphereDiameter = (V: number) => Math.cbrt((6 * V) / Math.PI);
export const surfaceRequired = (D: number, V: number) => (4 * V) / D + (Math.PI / 3) * D * D;

export function minCylindricalDiameter(V: number, S: number, areaStrain = 0): number {
  const Seff = S * (1 + areaStrain);
  const dSph = sphereDiameter(V);
  if (Seff <= surfaceRequired(dSph, V) + 1e-9) return dSph;
  // surfaceRequired decreases on (0, dSph]: bisection on f(D) = Sreq - Seff.
  let lo = 1e-3;
  let hi = dSph;
  for (let i = 0; i < 80; i++) {
    const mid = 0.5 * (lo + hi);
    if (surfaceRequired(mid, V) - Seff > 0) lo = mid;
    else hi = mid;
  }
  return 0.5 * (lo + hi);
}

export function capsuleShape(V: number, D: number): Capsule {
  const R = D / 2;
  const L = Math.max(0, (V - (4 / 3) * Math.PI * R ** 3) / (Math.PI * R * R));
  return {
    radius_um: R,
    cylinder_length_um: L,
    total_length_um: L + 2 * R,
    surface_um2: 2 * Math.PI * R * L + 4 * Math.PI * R * R,
  };
}

export function passage(V: number, S: number, D: number, stiffness: number | null = null): PassageResult {
  const Sreq = surfaceRequired(D, V);
  const strain = Math.max(0, Sreq / S - 1);
  let verdict: Verdict = "PASSES";
  if (strain > 0 && strain <= LYSIS_AREA_STRAIN) verdict = "PASSES_UNDER_STRAIN";
  else if (strain > LYSIS_AREA_STRAIN) verdict = "BLOCKED";
  let caveat = "";
  if (stiffness !== null && stiffness > 1 && verdict !== "BLOCKED") {
    caveat =
      `Geometric verdict only. Under the hypothesis of ${+stiffness.toFixed(2)}x normal stiffness, ` +
      "transit would be slower/harder; this is NOT quantified by this model and must be tested experimentally.";
  }
  return {
    capillary_diameter_um: D,
    mcd_um: minCylindricalDiameter(V, S),
    mcd_at_lysis_um: minCylindricalDiameter(V, S, LYSIS_AREA_STRAIN),
    surface_reserve: S / Sreq - 1,
    area_strain_needed: strain,
    verdict,
    stiffness_hypothesis: stiffness,
    caveat,
    provenance: "COMPUTED",
    capsule: capsuleShape(V, D),
  };
}

function efHalfThickness(x: number): number {
  const c = Math.min(Math.max(x, 0), 1);
  return 0.5 * Math.sqrt(Math.max(0, 1 - c * c)) * (EF_C0 + EF_C2 * c * c + EF_C4 * c ** 4);
}

function morphedProfile(t: number, R: number) {
  const s = R / EF_R0;
  return (r: number) => {
    const x = Math.min(Math.max(r / R, 0), 1);
    if (t < 0) return (1 + t) * s * efHalfThickness(x);
    return (1 - t) * s * efHalfThickness(x) + t * R * Math.sqrt(Math.max(0, 1 - x * x));
  };
}

/** Same vertex/face layout as mesh_cell() in Python (Y axis = thickness). */
export function meshCell(morphT: number, R: number, nTheta = 48, nPhi = 64): CellMesh {
  const h = morphedProfile(morphT, R);
  const vertices: [number, number, number][] = [];
  for (let i = 0; i <= nTheta; i++) {
    const th = (Math.PI * i) / nTheta;
    const r = R * Math.sin(th);
    const y = h(r) * (th <= Math.PI / 2 ? 1 : -1);
    if (i === 0 || i === nTheta) {
      vertices.push([0, y, 0]);
      continue;
    }
    for (let j = 0; j < nPhi; j++) {
      const p = (2 * Math.PI * j) / nPhi;
      vertices.push([r * Math.cos(p), y, r * Math.sin(p)]);
    }
  }
  const faces: [number, number, number][] = [];
  for (let j = 0; j < nPhi; j++) faces.push([0, 1 + ((j + 1) % nPhi), 1 + j]);
  const rings = nTheta - 1;
  for (let i = 0; i < rings - 1; i++) {
    const a0 = 1 + i * nPhi;
    const b0 = 1 + (i + 1) * nPhi;
    for (let j = 0; j < nPhi; j++) {
      const a = a0 + j, a2 = a0 + ((j + 1) % nPhi);
      const b = b0 + j, b2 = b0 + ((j + 1) % nPhi);
      faces.push([a, a2, b2]);
      faces.push([a, b2, b]);
    }
  }
  const bottom = vertices.length - 1;
  const last = 1 + (rings - 1) * nPhi;
  for (let j = 0; j < nPhi; j++) faces.push([bottom, last + j, last + ((j + 1) % nPhi)]);
  return { vertices, faces, units: "µm" };
}

/** Infer n_phi (segments) and ring count from a mesh_cell-style mesh. */
export function meshTopology(mesh: CellMesh): { nPhi: number; rings: number } | null {
  const nV = mesh.vertices.length;
  let nPhi = 0;
  for (const f of mesh.faces) if (f[0] === 0 || f[1] === 0 || f[2] === 0) nPhi++;
  if (nPhi < 3 || (nV - 2) % nPhi !== 0) return null;
  return { nPhi, rings: (nV - 2) / nPhi };
}

/**
 * Capsule target positions with the SAME topology as the cell mesh (top pole, rings, bottom pole).
 * Axis = local Y (the cell's symmetry axis); ring k sits at equal arc length along the capsule
 * meridian. Radius is capped by the sphere of volume V so the visual keeps the cell volume
 * when the tube is wider than the cell needs (the cell is then simply not confined).
 */
export function capsulePositions(mesh: CellMesh, V: number, D: number): Float32Array | null {
  const topo = meshTopology(mesh);
  if (!topo) return null;
  const { nPhi, rings } = topo;
  const R = Math.min(D / 2, sphereDiameter(V) / 2);
  const L = capsuleShape(V, 2 * R).cylinder_length_um;
  const quarter = (Math.PI * R) / 2;
  const total = 2 * quarter + L;
  const nTheta = rings + 1;
  const meridian = (s: number): [number, number] => {
    // s in [0, total] from top tip; returns [radius, y]
    if (s <= quarter) {
      const a = s / R;
      return [R * Math.sin(a), L / 2 + R * Math.cos(a)];
    }
    if (s <= quarter + L) return [R, L / 2 - (s - quarter)];
    const a = (s - quarter - L) / R;
    return [R * Math.cos(a), -L / 2 - R * Math.sin(a)];
  };
  const out = new Float32Array(mesh.vertices.length * 3);
  const setV = (idx: number, x: number, y: number, z: number) => {
    out[idx * 3] = x;
    out[idx * 3 + 1] = y;
    out[idx * 3 + 2] = z;
  };
  setV(0, 0, L / 2 + R, 0);
  for (let k = 0; k < rings; k++) {
    const [r, y] = meridian((total * (k + 1)) / nTheta);
    for (let j = 0; j < nPhi; j++) {
      const idx = 1 + k * nPhi + j;
      const v = mesh.vertices[idx];
      const phi = Math.atan2(v[2], v[0]);
      setV(idx, r * Math.cos(phi), y, r * Math.sin(phi));
    }
  }
  setV(mesh.vertices.length - 1, 0, -L / 2 - R, 0);
  return out;
}

/** ASCII STL, same format as write_stl(); vertices in µm, slicer reads mm -> scale 5 = x5000. */
export function meshToStl(mesh: CellMesh, scale = 5, name = "cell"): string {
  const v = mesh.vertices.map((p) => p.map((c) => c * scale));
  const lines: string[] = [`solid ${name}`];
  for (const [a, b, c] of mesh.faces) {
    const p0 = v[a], p1 = v[b], p2 = v[c];
    const u = [p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]];
    const w = [p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2]];
    let n = [u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]];
    const ln = Math.hypot(n[0], n[1], n[2]);
    if (ln > 0) n = n.map((x) => x / ln);
    lines.push(`facet normal ${n.map((x) => x.toExponential(6)).join(" ")}`, " outer loop");
    for (const p of [p0, p1, p2]) lines.push(`  vertex ${p.map((x) => x.toExponential(6)).join(" ")}`);
    lines.push(" endloop", "endfacet");
  }
  lines.push(`endsolid ${name}`);
  return lines.join("\n") + "\n";
}
