import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type { CellMesh, PassageResult } from "../types";
import { capsulePositions } from "../lib/physics";

// Scene units are µm. Tube axis = world +X, entrance at x = 0.
export const TUBE_LEN = 16;
const START_X = -6.5;
const END_X = TUBE_LEN + 6.5;
const REST_COLOR = new THREE.Color("#d23a3a");

export interface ActorSpec {
  key: string;
  label: string;
  labelColor: string;
  mesh: CellMesh | null;
  volume: number | null;
  passage: PassageResult | null;
}

interface SceneProps {
  actors: ActorSpec[];
  diameter: number;
  playToken: number; // increments on "Simulate passage"
  durationS: number; // set by the HYPOTHESIS stiffness slider: speed only
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(Math.max((x - a) / (b - a), 0), 1);
  return t * t * (3 - 2 * t);
};

export function strainColor(strain: number): THREE.Color {
  const t = Math.min(Math.max(strain / 0.03, 0), 1);
  return new THREE.Color().setHSL((120 * (1 - t)) / 360, 0.8, 0.5);
}

export function Scene3D({ actors, diameter, playToken, durationS }: SceneProps) {
  const spacing = 9;
  const n = actors.length;
  return (
    <Canvas camera={{ position: [6, 4, 24], fov: 40 }} dpr={[1, 2]} gl={{ antialias: true }}>
      <CameraRig rows={n} spacing={spacing} />
      <color attach="background" args={["#070a10"]} />
      <ambientLight intensity={0.45} />
      <directionalLight position={[10, 18, 14]} intensity={1.4} />
      <directionalLight position={[-12, -6, -10]} intensity={0.5} color="#88aaff" />
      <pointLight position={[8, 0, 8]} intensity={40} color="#ffd0d0" />
      {actors.map((a, i) => {
        const y = (i - (n - 1) / 2) * -spacing;
        return (
          <group key={a.key} position={[0, y, 0]}>
            <Tube diameter={diameter} blocked={a.passage?.verdict === "BLOCKED"} playToken={playToken} durationS={durationS} />
            {a.mesh && a.volume !== null && (
              <CellActor mesh={a.mesh} volume={a.volume} diameter={diameter} passage={a.passage} playToken={playToken} durationS={durationS} />
            )}
            {n > 1 && (
              <Html position={[TUBE_LEN / 2, Math.max(diameter, 3) / 2 + 3, 0]} center>
                <div className="scene-label" style={{ color: a.labelColor, borderColor: a.labelColor }}>
                  {a.label}
                </div>
              </Html>
            )}
          </group>
        );
      })}
      <OrbitControls makeDefault target={[CENTER_X, 0, 0]} enablePan={false} minDistance={8} maxDistance={90} />
    </Canvas>
  );
}

const CENTER_X = (START_X - 4 + END_X - 2) / 2;

/** Frame the whole stage (entrance to exit, all rows) for the current canvas aspect ratio. */
function CameraRig({ rows, spacing }: { rows: number; spacing: number }) {
  const { camera, size } = useThree();
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    const needW = END_X - START_X + 4;
    const needH = (rows - 1) * spacing + 10;
    const vfov = THREE.MathUtils.degToRad(cam.fov);
    const aspect = size.width / Math.max(size.height, 1);
    const distH = needH / 2 / Math.tan(vfov / 2);
    const distW = needW / 2 / (Math.tan(vfov / 2) * aspect);
    const d = Math.max(distH, distW) * 1.02;
    const dir = new THREE.Vector3(0.12, 0.28, 1).normalize();
    cam.position.set(CENTER_X + dir.x * d, dir.y * d, dir.z * d);
    cam.lookAt(CENTER_X, 0, 0);
    cam.updateProjectionMatrix();
  }, [camera, size.width, size.height, rows, spacing]);
  return null;
}

function Tube({ diameter, blocked, playToken, durationS }: { diameter: number; blocked: boolean; playToken: number; durationS: number }) {
  const mat = useRef<THREE.MeshStandardMaterial>(null);
  const start = useRef<number | null>(null);
  useEffect(() => {
    start.current = playToken > 0 ? performance.now() : null;
  }, [playToken]);
  useFrame(() => {
    const m = mat.current;
    if (!m) return;
    const t0 = start.current;
    const u = t0 === null ? 0 : (performance.now() - t0) / 1000 / durationS;
    if (blocked && t0 !== null && u > 0.3) {
      const blink = 0.5 + 0.5 * Math.sin(performance.now() / 120);
      m.color.set("#ff3030");
      m.emissive.set("#ff2020");
      m.emissiveIntensity = 0.3 + 0.9 * blink;
      m.opacity = 0.2 + 0.25 * blink;
    } else {
      m.color.set("#9fe8ff");
      m.emissive.set("#000000");
      m.emissiveIntensity = 0;
      m.opacity = 0.16;
    }
  });
  const r = diameter / 2;
  return (
    <group>
      <mesh rotation={[0, 0, -Math.PI / 2]} position={[TUBE_LEN / 2, 0, 0]}>
        <cylinderGeometry args={[r, r, TUBE_LEN, 48, 1, true]} />
        <meshStandardMaterial ref={mat} transparent opacity={0.16} color="#9fe8ff" side={THREE.DoubleSide} depthWrite={false} />
      </mesh>
      {[0, TUBE_LEN].map((x) => (
        <mesh key={x} position={[x, 0, 0]} rotation={[0, Math.PI / 2, 0]}>
          <torusGeometry args={[r, 0.07, 12, 64]} />
          <meshStandardMaterial color="#bff3ff" emissive="#3aa" emissiveIntensity={0.4} />
        </mesh>
      ))}
    </group>
  );
}

interface ActorProps {
  mesh: CellMesh;
  volume: number;
  diameter: number;
  passage: PassageResult | null;
  playToken: number;
  durationS: number;
}

function CellActor({ mesh, volume, diameter, passage, playToken, durationS }: ActorProps) {
  const outer = useRef<THREE.Group>(null);
  const matRef = useRef<THREE.MeshPhysicalMaterial>(null);

  const { geometry, rest } = useMemo(() => {
    const g = new THREE.BufferGeometry();
    const rest = new Float32Array(mesh.vertices.flat());
    g.setAttribute("position", new THREE.BufferAttribute(rest.slice(), 3));
    g.setIndex(mesh.faces.flat());
    g.computeVertexNormals();
    return { geometry: g, rest };
  }, [mesh]);
  useEffect(() => () => geometry.dispose(), [geometry]);

  const target = useMemo(() => capsulePositions(mesh, volume, diameter), [mesh, volume, diameter]);
  const halfCaps = useMemo(() => {
    if (!target) return 4;
    let m = 0;
    for (let i = 1; i < target.length; i += 3) m = Math.max(m, Math.abs(target[i]));
    return m;
  }, [target]);

  const start = useRef<number | null>(null);
  const lastMorph = useRef(-1);
  useEffect(() => {
    lastMorph.current = -1; // force a vertex update when the capsule target changes
  }, [target]);
  const idleAngle = useRef(0.7);
  useEffect(() => {
    start.current = playToken > 0 ? performance.now() : null;
  }, [playToken]);

  const verdict = passage?.verdict ?? "PASSES";
  const strain = passage?.area_strain_needed ?? 0;
  const strainCol = useMemo(() => strainColor(strain), [strain]);

  useFrame((_, dt) => {
    const g = outer.current;
    if (!g) return;
    const t0 = start.current;
    let x = START_X;
    let morph = 0;
    let align = 0;
    if (t0 === null) {
      idleAngle.current += dt * 0.5;
    } else {
      const u = Math.min((performance.now() - t0) / 1000 / durationS, 1);
      align = smooth(0, 0.15, u);
      if (verdict === "BLOCKED") {
        // Cell reaches the entrance, tries to deform, and stops there.
        x = THREE.MathUtils.lerp(START_X, -halfCaps * 0.35, smooth(0, 0.3, u));
        morph = 0.3 * smooth(0.2, 0.32, u);
      } else {
        const inX = halfCaps;
        const outX = TUBE_LEN - halfCaps;
        if (u < 0.2) x = THREE.MathUtils.lerp(START_X, -halfCaps * 0.5, smooth(0, 0.2, u));
        else if (u < 0.35) x = THREE.MathUtils.lerp(-halfCaps * 0.5, inX, (u - 0.2) / 0.15);
        else if (u < 0.8) x = THREE.MathUtils.lerp(inX, outX, (u - 0.35) / 0.45);
        else x = THREE.MathUtils.lerp(outX, END_X, smooth(0.8, 1, u));
        morph = smooth(0.18, 0.36, u) * (1 - smooth(0.8, 0.95, u));
      }
    }
    // Idle tumble about world Y; aligned (symmetry axis along the tube) during passage.
    const a = idleAngle.current % Math.PI;
    g.rotation.y = a * (1 - align);
    g.position.x = x;

    if (target && Math.abs(morph - lastMorph.current) > 1e-4) {
      const pos = geometry.attributes.position as THREE.BufferAttribute;
      const arr = pos.array as Float32Array;
      for (let i = 0; i < arr.length; i++) arr[i] = rest[i] + (target[i] - rest[i]) * morph;
      pos.needsUpdate = true;
      geometry.computeVertexNormals();
      geometry.computeBoundingSphere();
      lastMorph.current = morph;
    }
    const m = matRef.current;
    if (m) {
      const c = t0 === null ? 0 : Math.min(1, morph * 3 + (verdict === "BLOCKED" ? 1 : 0));
      m.color.copy(REST_COLOR).lerp(strainCol, c);
      m.emissive.copy(m.color).multiplyScalar(0.18);
    }
  });

  return (
    <group ref={outer} position={[START_X, 0, 0]}>
      <group rotation={[0, 0, -Math.PI / 2]}>
        <mesh geometry={geometry}>
          <meshPhysicalMaterial
            ref={matRef}
            color={REST_COLOR}
            roughness={0.45}
            clearcoat={0.4}
            transparent
            opacity={0.88}
            side={THREE.DoubleSide}
          />
        </mesh>
      </group>
    </group>
  );
}
