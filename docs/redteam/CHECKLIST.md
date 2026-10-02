# CellLab : checklist finale avant la présentation

Cochée ici le 2026-10-02 pour ce qui se vérifie dans le conteneur (API locale, fichiers, tests). Les cases vides demandent la machine de démo, une clé API, un projecteur ou un slicer : elles sont pour l'équipe, avec un responsable proposé.

## A. Vérifié ici

- [x] **Tests** : `python3 -m pytest -q tests/` → 58 passed ; `celllab_physics.py --selftest` → ALL TESTS PASSED.
- [x] **API** : `/api/health` → `{"status":"ok"}` ; `/api/samples` liste 5 échantillons (3 Chula, 2 synthétiques), chacun avec son D50 étiqueté COMPUTED (3,02 / 3,48 / 3,81 / 2,99 / 3,16 µm).
- [x] **Passage** : `/passage` répond pour c112 (chula_102) et c132 (chula_264). À 3,30 µm : c132 PASSES, c112 BLOCKED (4,9 %). À 10 et 20 µm : PASSES avec `"unconfined": true`. `d = 0,3` refusé (422).
- [x] **Replays** : `demo/replay_main.jsonl` (36 événements) et `demo/replay_guard.jsonl` (39) se parsent et sont servis par `/api/replay/{name}`, avec un événement `report` final. `frontend/public/mocks/replay_main.jsonl` est identique à `demo/replay_main.jsonl`. Les données des 3 Chula existent aussi en mock (`frontend/public/mocks/samples/`), donc l'interface peut tourner sans API.
- [x] **STL** (`demo/*.stl` et `/stl` de l'API) : maillages fermés, orientés vers l'extérieur, sans triangle dégénéré (Euler 2, 0 arête non manifold, 6 016 triangles, ASCII).
  - discocyte du pack : 38,9 × 12,4 × 38,9 mm (≈ 4 cm), volume réel 89,7 fL ;
  - sphérocyte du pack : 32,3 × 15,0 × 32,3 mm, 79,8 fL ;
  - c112 (chula_102) : 28,9 × 14,3 × 28,9 mm, 61,3 fL (≈ 3 cm : normal, c'est une petite cellule) ;
  - c003 (chula_264) : 42,9 × 13,6 × 42,9 mm.
- [x] **Aucune ressource réseau** dans `frontend/src` ni `index.html` (pas de police ou de CDN externe) : le replay peut tourner sans Wi-Fi, une fois `node_modules` installé.
- [x] **Étiquettes visibles** (captures) : « DEMO VALUES » sur les NFS, « SYNTHETIC » / « SYNTHETIC DEMO DATA » sur les synthétiques, « REPLAY » en mode replay, provenance sur chaque nombre.

## B. Non vérifiable ici : à faire par l'équipe

### Agent et replay (Nolann, avec la clé)
- [ ] Enregistrer un **vrai** run sur la paire de démo : `python -m backend.agent.orchestrator --samples chula_264 chula_102 --record demo/replay_main.jsonl`, puis le copier dans `frontend/public/mocks/replay_main.jsonl`. Vérifier que le premier événement n'est plus `"mode": "scripted"`.
- [ ] Enregistrer aussi un vrai run de refus du guard (`demo/replay_guard.jsonl`), ou garder le scripté et le présenter comme tel.
- [ ] Chronométrer **3 runs live** (temps jusqu'à l'événement `report`) et reporter la valeur dans `07_PITCH_FINAL.md` (cible < 60 s).
- [ ] Relire le rapport live : remplacer chaque **[live]** du pitch par la valeur affichée (fraction de la sous-population, nombre de valeurs vérifiées par le guard, largeurs et pourcentages de la carte).
- [ ] Vérifier que le rapport live ne montre pas c040 (V 189 fL) comme cellule « worst ». Sinon, montrer c112 à la main.
- [ ] Tant que le replay est scripté : ne **pas** dire « a run we recorded this morning ».

### Machine de démo (X, frontend)
- [ ] `cd frontend && npm install` **avant** de couper le réseau ; `npm run build` passe (`tsc -b`). Non testable ici : `node_modules` absent.
- [ ] Live : `uvicorn backend.api.app:app --port 8000` puis `npm run dev`, URL `http://localhost:5173/?mode=live&a=chula_264&b=chula_102`. Pastille LIVE verte, deux images Chula, D50 3,02 et 3,81.
- [ ] **Curseur du canal sur 3,30 µm** avant « Healthy vs test ». À 3,00 µm, la cellule A par défaut (c132) sort BLOCKED.
- [ ] Touche **L** : la trace live défile et le rapport arrive dans le panneau de droite.
- [ ] Replay **sans Wi-Fi** : Wi-Fi coupé, API arrêtée, `?mode=replay&a=chula_264&b=chula_102` ; touche **R** ; la trace et le rapport s'affichent, la vue 3D tourne (passage calculé en local). Attention : si le replay est encore le run scripté sur synthétiques, la trace parlera de `synthetic_hs` alors que les panneaux montrent Chula. Dans ce cas, utiliser `?mode=replay` sans `a` ni `b`.
- [ ] Téléchargement STL depuis l'interface : le fichier s'ouvre.
- [ ] Si le temps le permet (`redteam_product_v2.md`) : « 0 invented » → « 0 untraced » (P8), légende de la barre 0,74 tronquée (P9), badge « SCRIPTED » (P1).

### Écran et salle
- [ ] Résolution **1280×720** (ou navigateur à 1280×720, zoom 100 %) ; vérifier que la ligne NFS « RDW » n'est pas coupée (P18).
- [ ] Test sur le **projecteur** de la salle : contraste des badges de provenance (jaune et rose sur fond sombre), taille des D50 lisible du fond.
- [ ] Mode sombre du système sans effet sur l'app ; notifications coupées ; veille désactivée.
- [ ] **Batterie chargée** à 100 % et chargeur branché ; second ordinateur prêt avec le même état.
- [ ] Vidéo de secours (≤ 3 min) enregistrée à partir d'un run réussi, sur la clé USB et sur le bureau.

### Objet imprimé
- [ ] Les deux STL du pack s'ouvrent dans le **slicer** (Cura, PrusaSlicer ou Bambu) sans erreur de réparation ; taille affichée ≈ 39 mm et 32 mm.
- [ ] Impression faite, objets dans le sac.

### Pitch
- [ ] Chronométré **à voix haute** 2 fois, sous 3:00 avec les clics (texte : 415 mots, 2 min 46 s à 150 mots/min).
- [ ] Réponses Q11 à Q16 de `07_PITCH_FINAL.md` lues par toute l'équipe.
- [ ] Citation Chula ajoutée au README (P14) et présente sur la slide 2.
- [ ] Corrections de `02` faites par le lead (P13), au cas où un juré l'ouvre.
