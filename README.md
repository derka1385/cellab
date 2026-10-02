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
