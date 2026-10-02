// THE data switch. One line to change for the demo:
//   "mock"   : everything from static files in public/mocks/ (no backend, no network)
//   "live"   : everything from the FastAPI backend (/api, proxied by Vite), agent run by polling
//   "replay" : samples/mesh/passage from the API (falling back to mocks if it is down),
//              agent trace replayed from public/mocks/replay_main.jsonl (no Claude call, no Wi-Fi)
// Override without editing: URL ?mode=live, or env VITE_CELLLAB_MODE=live.
export type DataMode = "mock" | "live" | "replay";

export const DEFAULT_MODE: DataMode = "mock";

export const SAMPLE_A = "synthetic_healthy"; // reference ("healthy") sample
export const SAMPLE_B = "synthetic_hs"; // test sample

export const REPLAY_FILE = "/mocks/replay_main.jsonl";
export const POLL_MS = 500;

const MODES: DataMode[] = ["mock", "live", "replay"];

export function initialMode(): DataMode {
  const url = new URLSearchParams(window.location.search).get("mode");
  if (url && (MODES as string[]).includes(url)) return url as DataMode;
  const env = import.meta.env.VITE_CELLLAB_MODE as string | undefined;
  if (env && (MODES as string[]).includes(env)) return env as DataMode;
  return DEFAULT_MODE;
}

export function initialSamples(): [string, string] {
  const q = new URLSearchParams(window.location.search);
  return [q.get("a") ?? SAMPLE_A, q.get("b") ?? SAMPLE_B];
}
