#!/usr/bin/env bash
# scaffold_celllab.sh — creates the CellLab repo skeleton (03_ARCHITECTURE_ET_CONTRATS.md, section 3).
#
# Usage:
#   bash scaffold_celllab.sh [PACK_DIR] [TARGET_DIR]
#     PACK_DIR   folder holding 01_..07_*.md and celllab_physics.py (default: current dir)
#     TARGET_DIR repo to create (default: ./celllab)
#
# Idempotent: existing files are NEVER overwritten (safe to re-run on a repo in progress).
set -euo pipefail

PACK_DIR="$(cd "${1:-.}" && pwd)"
TARGET="${2:-./celllab}"
mkdir -p "$TARGET"
TARGET="$(cd "$TARGET" && pwd)"

# Find a pack file by suffix, tolerating upload prefixes like "1a2b3c-04_AGENTS.md".
find_pack() {
  local f
  f=$(find "$PACK_DIR" -maxdepth 2 -type f -name "*$1" | head -n 1)
  echo "$f"
}

# Write stdin to $1 only if it does not exist yet.
write_new() {
  local path="$TARGET/$1"
  mkdir -p "$(dirname "$path")"
  if [[ -e "$path" ]]; then
    cat > /dev/null
    echo "  keep   $1"
  else
    cat > "$path"
    echo "  create $1"
  fi
}

copy_new() {  # copy_new <src> <dest-relative>
  local src="$1" dest="$TARGET/$2"
  if [[ -z "$src" || ! -f "$src" ]]; then echo "  MISSING source for $2"; return 0; fi
  mkdir -p "$(dirname "$dest")"
  if [[ -e "$dest" ]]; then echo "  keep   $2"; else cp "$src" "$dest"; echo "  create $2"; fi
}

echo "==> Directories"
mkdir -p "$TARGET"/{docs,scripts,tests,demo} \
         "$TARGET"/backend/{physics,vision,agent,api} \
         "$TARGET"/backend/data/{samples,runs,validation} \
         "$TARGET"/frontend/{public/mocks,src}

echo "==> Physics core + docs"
PHYS=$(find_pack "celllab_physics.py")
if [[ -z "$PHYS" ]]; then echo "ERROR: celllab_physics.py not found in $PACK_DIR" >&2; exit 1; fi
copy_new "$PHYS" "backend/physics/celllab_physics.py"
for doc in 00_LISEZ-MOI.md 01_INSTRUCTIONS_PROJET.md 02_CONTEXTE_SCIENTIFIQUE.md \
           03_ARCHITECTURE_ET_CONTRATS.md 04_AGENTS.md 05_PROMPT_DE_LANCEMENT.md \
           06_PLAN_HEURE_PAR_HEURE.md 07_PITCH_ET_QUESTIONS_JURY.md passage_curve_demo.png; do
  copy_new "$(find_pack "$doc")" "docs/$doc"
done
copy_new "$(find_pack 01_INSTRUCTIONS_PROJET.md)" "CLAUDE.md"
for stl in healthy_discocyte_x5000.stl spherocyte_x5000.stl; do
  copy_new "$(find_pack "$stl")" "demo/$stl"
done

echo "==> Python packages (so 'python -m backend.x' and 'uvicorn backend.api.app:app' work)"
for pkg in backend backend/physics backend/vision backend/agent backend/api; do
  write_new "$pkg/__init__.py" < /dev/null
done
touch "$TARGET/backend/data/samples/.gitkeep" "$TARGET/backend/data/runs/.gitkeep"

write_new "backend/api/app.py" <<'EOF'
"""CellLab API. Placeholder: the PIPELINE agent replaces this with every route of section 6."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="CellLab API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
EOF

echo "==> requirements"
write_new "requirements.txt" <<'EOF'
# Physics core (np.trapezoid needs numpy >= 2.0)
numpy>=2.0
scipy>=1.11
matplotlib>=3.8
# Vision (fallback path: Otsu + watershed, no GPU needed)
scikit-image>=0.22
opencv-python-headless>=4.9
pillow>=10.0
# API
fastapi>=0.110
uvicorn[standard]>=0.29
# Agent
anthropic>=0.40
python-dotenv>=1.0
# Tests
pytest>=8.0
httpx>=0.27
EOF

write_new "requirements-cellpose.txt" <<'EOF'
# Optional vision path A. Pulls PyTorch (~1 GB). Install only if the fallback is not good enough:
#   pip install -r requirements-cellpose.txt && pip show cellpose
cellpose>=4.0
EOF

echo "==> Frontend (Vite + React + TS + r3f + drei + Recharts)"
write_new "frontend/package.json" <<'EOF'
{
  "name": "celllab-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "@react-three/drei": "^9.122.0",
    "@react-three/fiber": "^8.18.0",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.15.0",
    "three": "^0.170.0"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@types/three": "^0.170.0",
    "@vitejs/plugin-react": "^4.7.0",
    "typescript": "^5.6.3",
    "vite": "^5.4.21"
  }
}
EOF

write_new "frontend/vite.config.ts" <<'EOF'
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// /api is proxied to FastAPI so the frontend never hardcodes the backend URL.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
});
EOF

write_new "frontend/tsconfig.json" <<'EOF'
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true
  },
  "include": ["src"]
}
EOF

write_new "frontend/index.html" <<'EOF'
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>CellLab</title>
  </head>
  <body style="margin:0;background:#0b0f17;color:#e6edf3">
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
EOF

write_new "frontend/src/main.tsx" <<'EOF'
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
EOF

write_new "frontend/src/App.tsx" <<'EOF'
// Placeholder screen. The FRONTEND agent replaces this with the single-screen layout (section 7).
export default function App() {
  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 32, fontSize: 18 }}>
      <h1>CellLab</h1>
      <p>Run experiments on cells before touching the cells.</p>
    </main>
  );
}
EOF

echo "==> Config files"
write_new ".env.example" <<'EOF'
# Copy to .env and fill in. Never commit .env.
ANTHROPIC_API_KEY=
CELLLAB_MODEL=claude-sonnet-5-5
EOF

write_new ".gitignore" <<'EOF'
# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
# Secrets
.env
# Node
frontend/node_modules/
frontend/dist/
# Data: downloaded dataset and generated runs stay local
external/
backend/data/runs/*
!backend/data/runs/.gitkeep
backend/data/samples/*/population.json
# OS / editors
.DS_Store
.idea/
.vscode/
EOF

write_new "README.md" <<'EOF'
# CellLab

> Run experiments on cells before touching the cells.

CellLab is a research agent that turns a blood smear image and a blood count (CBC) into
geometric digital twins of red blood cells, runs a virtual capillary-passage experiment on the
whole population, and proposes a falsifiable microfluidic experiment.
Research hypothesis tool only, not a medical device. Demo CBC values and synthetic data are labelled.

## Quick start
    python3.11 -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    python backend/physics/celllab_physics.py --selftest   # 19 checks, all OK
    cp .env.example .env                                   # add ANTHROPIC_API_KEY
    uvicorn backend.api.app:app --reload                   # http://127.0.0.1:8000/docs
    cd frontend && npm install && npm run dev              # http://localhost:5173

## Layout
backend/physics (geometric core), backend/vision (smear -> sample.json), backend/agent (Claude
tool-use loop + number_guard), backend/api (FastAPI), frontend (React + three.js), demo (replay, STL).
Contracts: docs/03_ARCHITECTURE_ET_CONTRATS.md. Every number carries a provenance tag.
EOF

chmod +x "$0" 2>/dev/null || true
echo
echo "Done: $TARGET"
echo "Next: cd $TARGET && python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
