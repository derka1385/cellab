# CellLab — Architecture et contrats

Ce document fait foi pour toutes les interfaces. Chaque module peut être développé en parallèle tant qu'il respecte ces contrats. **Tout changement de contrat est annoncé à toute l'équipe avant d'être codé.**

## 1. Vue d'ensemble

```
 Image de frottis ──► [VISION] ──► sample.json (MEASURED)
 NFS de démo ───────────────────► cbc.json (CONSTRAINED)
                                       │
                                       ▼
                    [PHYSICS] celllab_physics.py  (INFERRED + COMPUTED)
                                       ▲
                                       │ outils déterministes
                    [AGENT] Claude + tool use ──► trace.jsonl + report.json
                                       │
                                       ▼
                    [API] FastAPI ──► [FRONTEND] React + Three.js
                                       │
                                       └──► mode REPLAY (trace enregistrée, sans réseau)
```

## 2. Stack

| Couche | Choix principal | Repli si l'équipe bloque |
|---|---|---|
| Vision | Python, `cellpose` (vérifier la version : l'API a changé avec Cellpose 4 / Cellpose-SAM), `scikit-image`, `opencv-python` | Seuillage d'Otsu + distance transform + watershed (`scikit-image`), suffisant pour des globules rouges sur frottis |
| Physique | `celllab_physics.py` (numpy, scipy), **déjà testé** | Aucun repli nécessaire |
| Agent | SDK Python `anthropic`, Messages API avec tool use, modèle `claude-sonnet-5-5` (rapide) ou `claude-opus-5-5` (qualité) | Mode replay |
| API | FastAPI + uvicorn, polling simple (pas de websockets) | Fichiers JSON statiques servis par le frontend |
| Frontend | Vite + React + `@react-three/fiber` + `@react-three/drei` + Recharts | Streamlit + Plotly `Mesh3d` (moins beau mais rapide) |
| Export 3D | STL ASCII via `write_stl` (déjà codé) | — |

## 3. Arborescence du repo

```
celllab/
├── CLAUDE.md                     # = 01_INSTRUCTIONS_PROJET.md (si Claude Code)
├── docs/                         # les fichiers de ce pack
├── backend/
│   ├── physics/celllab_physics.py
│   ├── vision/
│   │   ├── segment.py            # image -> masques
│   │   ├── measure.py            # masques -> sample.json
│   │   ├── chula_loader.py       # lecture des annotations Chula RBC-12
│   │   └── validate_pallor.py    # pâleur/SI vs classes annotées -> validation.json
│   ├── agent/
│   │   ├── tools.py              # outils déterministes + schémas JSON
│   │   ├── orchestrator.py       # boucle tool use
│   │   ├── prompts.py            # prompt système de l'agent
│   │   └── number_guard.py       # vérifie que chaque nombre du rapport vient d'un outil
│   ├── api/app.py                # FastAPI
│   └── data/
│       ├── samples/<sample_id>/{image.png, sample.json, cbc.json, population.json}
│       └── runs/<run_id>/{trace.jsonl, report.json}
├── frontend/                     # Vite + React
└── demo/
    ├── replay_main.jsonl         # exécution de référence pour la démo hors ligne
    └── cellLab_rbc_x5000.stl
```

## 4. Contrats de données

### 4.1 `sample.json` (VISION → PHYSICS) — tout est MEASURED

```json
{
  "sample_id": "chula_0123",
  "label": "Chula RBC-12 image 0123",
  "image_path": "data/samples/chula_0123/image.png",
  "pixel_size_um": null,
  "source": "public_dataset",
  "cells": [
    {
      "cell_id": "c001",
      "centroid_px": [312.4, 188.0],
      "bbox_px": [290, 166, 45, 44],
      "contour_px": [[290, 188], [291, 180]],
      "area": 1540.0,
      "diameter": 44.3,
      "circularity": 0.93,
      "pallor_ratio": 0.38,
      "shape_class": "normal",
      "shape_class_source": "annotation",
      "excluded": false,
      "exclusion_reason": null
    }
  ]
}
```

Règles :
- `area` et `diameter` sont en pixels si `pixel_size_um` vaut `null`. **Seuls les rapports comptent** (la NFS fixe l'échelle), donc ce n'est pas bloquant.
- `pallor_ratio` = diamètre équivalent de la zone de pâleur centrale / diamètre de la cellule. Il vaut 0 si la cellule n'a pas de pâleur.
- `shape_class_source` ∈ `annotation` (Chula), `classifier`, `none`.
- Exclure (`excluded: true`) les cellules qui touchent le bord, les amas qui se chevauchent (circularité < 0,6 ou aire > 2× la médiane), et les globules blancs ou plaquettes. Toujours renseigner `exclusion_reason`.
- Pour appeler la physique : `CellMeasurement(cell_id, area_um2=area, diameter_um=diameter, circularity, pallor_ratio, shape_class)`.

### 4.2 `cbc.json` — CONSTRAINED

```json
{ "mcv_fl": 84.0, "rdw_cv_pct": 17.5, "mchc_g_dl": 37.2, "source": "demo", "note": "Demo values, not patient data" }
```

### 4.3 `population.json` (PHYSICS → FRONTEND et AGENT)

```json
{
  "sample_id": "chula_0123",
  "cells": [ "… sortie de infer_population() + champs shape et passage ci-dessous …" ],
  "cell_extra": {
    "c001": {
      "shape": { "morph_t": -0.03, "radius_um": 3.89, "provenance": "INFERRED" },
      "passage_at_3um": { "verdict": "PASSES", "area_strain_needed": 0.0, "provenance": "COMPUTED" }
    }
  },
  "sweep": { "diameters_um": [], "passes": [], "passes_under_strain": [], "blocked": [], "provenance": "COMPUTED" },
  "d50_um": 2.94,
  "consistency": [ { "check": "RDW_vs_diameter_CV", "status": "COHERENT" } ],
  "synthetic": false
}
```

Chaque nombre exposé à l'interface est un objet `{ "value", "unit", "provenance", "note" }` (classe `Tagged`), sauf à l'intérieur des tableaux `sweep`, dont la provenance est portée par le bloc.

### 4.4 Trace de l'agent `trace.jsonl` (une ligne = un événement)

```json
{"seq": 1, "t": 0.0,  "type": "plan",        "text": "I will compare both samples, check CBC coherence, then sweep channel widths."}
{"seq": 2, "t": 1.2,  "type": "tool_call",   "id": "tc_01", "tool": "infer_geometry", "input": {"sample_id": "A"}}
{"seq": 3, "t": 2.9,  "type": "tool_result", "id": "tc_01", "output": {"n_cells": 212, "si_p90": 0.81}}
{"seq": 9, "t": 21.4, "type": "report",      "report_path": "data/runs/r001/report.json"}
```

Le frontend rejoue ce fichier événement par événement, ce qui permet le **mode replay** : même affichage, sans réseau.

### 4.5 `report.json` — sortie finale de l'agent

```json
{
  "title": "Sample B shows a spherical subpopulation that fails 3.1 µm channels",
  "summary": "…",
  "findings": [
    {
      "text": "31% of cells in sample B have a sphericity index above 0.85, versus 2% in sample A.",
      "numbers": [
        { "value": 0.31, "unit": "fraction", "provenance": "COMPUTED", "tool_call_id": "tc_04" },
        { "value": 0.85, "unit": "", "provenance": "HYPOTHESIS", "tool_call_id": null }
      ]
    }
  ],
  "consistency_flags": [],
  "experiment": { "…": "sortie de design_experiment()" },
  "limitations": ["Sphericity is inferred from central pallor.", "No mechanical simulation."],
  "number_guard": { "checked": 14, "unverified": 0 }
}
```

## 5. Outils de l'agent (`backend/agent/tools.py`)

Tous les outils sont **déterministes** et renvoient du JSON compact : des résumés et des quantiles, jamais 200 cellules brutes, pour garder le contexte du LLM léger.

| Outil | Entrée | Sortie (résumé) |
|---|---|---|
| `list_samples` | — | ids, labels, présence de la NFS, nombre de cellules |
| `measure_sample` | `sample_id` | nombre de cellules gardées et exclues, distribution de la pâleur, quantiles du diamètre |
| `infer_geometry` | `sample_id` | quantiles de V, S, SI et MCD ; fraction de cellules avec SI > seuil |
| `check_cbc_consistency` | `sample_id` | sortie de `cbc_consistency()` |
| `sweep_channels` | `sample_ids[]`, `d_min`, `d_max` | D50 par échantillon ; fractions qui passent à 2,5 / 3,0 / 3,5 / 4,0 µm |
| `find_subpopulation` | `sample_id`, `si_threshold` | fraction, MCD médian de la sous-population, ids de 3 exemples |
| `simulate_cell` | `sample_id`, `cell_id`, `diameter_um`, `stiffness_hypothesis?` | sortie de `passage()` + `capsule_shape()` |
| `select_cells_for_display` | `sample_id`, `strategy` ∈ `typical`, `worst`, `borderline` | ids de cellules + raison du choix |
| `design_experiment` | `sample_a`, `sample_b` | sortie de `design_experiment()` |
| `submit_report` | `report` (schéma 4.5) | `number_guard` exécuté ; refus avec liste des nombres non vérifiés si nécessaire |

### `number_guard`

Il extrait tous les nombres du texte du rapport et vérifie que chacun apparaît (à l'arrondi près) dans au moins un résultat d'outil de l'exécution, ou qu'il est déclaré `HYPOTHESIS`. Si un nombre n'est pas vérifié, `submit_report` renvoie une erreur à l'agent, qui doit corriger. **C'est un argument de pitch** : « 0 nombre inventé ».

## 6. API (`backend/api/app.py`)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/api/samples` | liste des échantillons |
| GET | `/api/samples/{id}` | `sample.json` + `cbc.json` + `population.json` |
| GET | `/api/samples/{id}/image` | image du frottis |
| GET | `/api/samples/{id}/cells/{cell_id}/mesh` | maillage JSON (`mesh_cell`) |
| GET | `/api/samples/{id}/cells/{cell_id}/passage?d=3.0&stiffness=1` | verdict + capsule (pour le curseur en direct) |
| POST | `/api/agent/run` | `{ "sample_ids": [...], "question": "..." }` → `{ "run_id" }` |
| GET | `/api/agent/run/{run_id}/events?after=<seq>` | événements de trace (polling toutes les 500 ms) |
| GET | `/api/replay/{name}` | trace enregistrée, pour la démo hors ligne |
| GET | `/api/samples/{id}/cells/{cell_id}/stl` | téléchargement STL ×5000 |

## 7. Interface (un seul écran)

```
┌──────────────────────┬──────────────────────────────┬─────────────────────────┐
│ ÉCHANTILLONS         │   VUE 3D                      │ COURBE DE PASSAGE       │
│ A: sain   B: test    │   cellule + capillaire        │ % qui passent vs D (µm) │
│ image + contours     │   curseur D (2–5 µm)          │ A (bleu) vs B (rouge)   │
│ NFS (CONSTRAINED)    │   curseur rigidité (HYPOTHESIS)│ histogramme SI          │
├──────────────────────┤   jauge d'étirement 0→3 %     ├─────────────────────────┤
│ AGENT (trace live)   │   verdict PASSES/STRAIN/BLOCK │ RAPPORT + badges        │
│ plan → outils → …    │                               │ proposition d'expérience│
└──────────────────────┴──────────────────────────────┴─────────────────────────┘
```

Badges de provenance (cohérents partout) :

| Badge | Couleur | Sens |
|---|---|---|
| MEASURED | vert | lu sur l'image |
| CONSTRAINED | bleu | fixé par la NFS |
| INFERRED | ambre | sortie de modèle |
| COMPUTED | violet | physique déterministe |
| HYPOTHESIS | rose, bord en pointillés | choisi pour explorer |
