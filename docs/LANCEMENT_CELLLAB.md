# CellLab — Lancement (réponse au prompt de lancement)

Valeurs d'équipe retenues par défaut (le prompt avait encore les exemples entre crochets) : 24 h samedi 10 h → dimanche 10 h, 3 personnes (Nolann agent + pitch + pipeline, X frontend, Y vision), MacBook sans GPU, Python 3.11, Node 20.

## 1. Vérification express

1. CellLab est un agent de recherche : frottis + NFS → jumeaux géométriques (V, S) de chaque globule rouge → balayage virtuel de diamètres de canal → expérience microfluidique falsifiable. Pas de diagnostic, pas de rigidité prédite.
2. La physique est géométrique (capsule de Canham-Burton, lyse à 3 % d'étirement de surface) et déjà testée : `celllab_physics.py --selftest` passe ses 19 contrôles ici (numpy 2.4, scipy 1.17).
3. Contrats : `sample.json` (VISION, MEASURED, pixels acceptés) + `cbc.json` (CONSTRAINED) → `population.json` (INFERRED/COMPUTED, nombres en objets `Tagged`) → agent (`trace.jsonl` + `report.json`) → API FastAPI → frontend React/three.js, avec un mode replay sans réseau.
4. Provenance : MEASURED (image), CONSTRAINED (NFS), INFERRED (modèle), COMPUTED (physique), HYPOTHESIS (choix « et si »). Une valeur sans étiquette est un bug ; le LLM ne produit aucun nombre, `number_guard` refuse tout rapport avec un nombre non tracé.
5. La seule hypothèse forte est pâleur centrale → sphéricité ; elle doit être validée sur Chula RBC-12 (AUC rapportée honnêtement) et dite pendant le pitch.

## 2. Incohérences relevées

| # | Gravité | Où | Problème | Correction appliquée ou proposée |
|---|---|---|---|---|
| 1 | Important | `02` §2 | « V 90–94 fL, S 131–135 µm² → MCD 2,9–3,0 µm » : le code donne 2,85 (90 ; 135) à 3,11 (94 ; 131). Seul le discocyte d'Evans-Fung (94,1 ; 134,1) donne 3,02. | Remplacer par « MCD ≈ 3,0 µm pour le discocyte moyen d'Evans-Fung (3,02 µm) ». Le pitch (« 3.0 µm for a normal cell ») reste juste. |
| 2 | Important | `02` §2, pitch | Avec la cellule moyenne de Namvar (V 99, S 149), le modèle donne 2,81 µm, alors que Namvar mesure 3,03 ± 0,21. Un juré qui fait le calcul le verra. | Réponse corrigée après red team : l'argument « moyenne des MCD » ne tient pas (2,82 µm). Dire que notre MCD est une borne géométrique inférieure (2,81 contre 3,03 ± 0,21, à ~1 écart-type, et Namvar mesure un point de blocage dans des canaux en coin). Dans le pitch, citer Evans-Fung (3,02 µm) et retirer « matches ». |
| 3 | Important | `02` §1 vs code | « Carence en fer → sphéricité plus basse » : `si_from_pallor` plafonne la pâleur à 0,40 (SI minimum 0,74), donc le pipeline ne peut jamais produire de cellule plus plate que la normale. | Retirer la ligne du tableau ou étendre l'interpolation au-delà de 0,40 (le selftest doit rester vert). |
| 4 | Important | `03` §4.1 vs physique | Si `pixel_size_um` est `null`, `infer_population` étiquette quand même l'aire en « µm² » et le diamètre en « µm ». | Le pipeline réécrit les unités en `px²` / `px` (consigne donnée à l'agent 2). |
| 5 | Mineur | `03` §4.3 | `d50_um` est un nombre nu, alors que la règle dit que tout nombre exposé est un `Tagged`. | On garde `d50_um` et on ajoute `d50` en `Tagged` (consigne donnée à l'agent 2). |
| 6 | Mineur | `03` §3 vs `04` | L'arborescence n'a ni `backend/pipeline.py`, ni `tests/`, ni `scripts/`, ni d'emplacement pour `validation.json`, que les briefs demandent. Il manque aussi les `__init__.py` nécessaires à `python -m backend.vision.measure` et `uvicorn backend.api.app:app`. | Ajoutés par le script de squelette (`backend/data/validation/` pour la validation). |
| 7 | Mineur | `03` §4.1 | Les populations synthétiques (V, S) ne passent pas par `sample.json`, alors que `population.json` sort de `infer_population()`. | L'agent 2 génère un `sample.json` synthétique conforme (aire ∝ V^2/3, pâleur inverse de `si_from_pallor`), puis passe par le même pipeline. |
| 8 | Mineur | `00` vs `03` §3 | `00` parle d'un dossier `exemples/` avec deux STL ; `03` attend `demo/cellLab_rbc_x5000.stl`. | Les deux STL du pack sont copiés dans `demo/`. |
| 9 | Mineur | `requirements` | `celllab_physics.py` utilise `np.trapezoid`, absent avant numpy 2.0. | `numpy>=2.0` dans `requirements.txt`. |
| 11 | Important | `celllab_physics.py` `passage()` | Le modèle capsule ne vaut que si la cellule est confinée : au-delà du diamètre de la sphère de même volume, `surface_required` remonte. Une cellule normale ressort BLOCKED dans un canal de 10 µm. | L'API évalue au diamètre de la sphère et renvoie `"unconfined": true`. Le balayage 2–5 µm n'est pas touché. À corriger dans la physique (selftest vert). |
| 10 | À vérifier | règlement | Du code est généré avant le début du hackathon. | Vérifier que le règlement autorise le code préparé à l'avance. |

## 3. Squelette du repo

Script complet : `scaffold_celllab.sh` (à la racine du repo). Il ne remplace jamais un fichier existant, donc on peut le relancer sans risque. Il a été testé ici de bout en bout : selftest vert, `uvicorn` répond sur `/api/health`, `tsc` passe, `vite` sert la page.

### Ordre exact des commandes (sur chaque MacBook)

```bash
# 0. Récupérer le pack (dossier contenant 01..07 + celllab_physics.py) puis :
bash scaffold_celllab.sh ./pack ./celllab
cd celllab
git init && git add -A && git commit -m "CellLab skeleton"

# 1. Python
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python backend/physics/celllab_physics.py --selftest     # attendu : ALL TESTS PASSED

# 2. Clé API
cp .env.example .env        # puis renseigner ANTHROPIC_API_KEY

# 3. API (terminal 1)
uvicorn backend.api.app:app --reload
curl -s localhost:8000/api/health                        # attendu : {"status":"ok"}

# 4. Frontend (terminal 2, Node 20)
cd frontend && npm install && npm run dev                # http://localhost:5173

# 5. Tests (une fois l'agent 2 livré)
pytest -q
```

Optionnel, seulement si Y en a besoin : `pip install -r requirements-cellpose.txt && pip show cellpose` (installe PyTorch, environ 1 Go).

## 4. Plan adapté

Voir `docs/06_PLAN_ADAPTE_24H_3P.md`.
