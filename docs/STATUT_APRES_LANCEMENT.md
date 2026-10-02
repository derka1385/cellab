# CellLab — État après le lancement des 5 agents (2 octobre 2026)

Tout est dans `/mnt/project-files/celllab/`. Vérifié ici : `pytest` 58 tests verts, selftest physique vert, `npm run typecheck` et `npm run build` verts, API + frontend testés ensemble en live sur les échantillons Chula et en replay (captures `frontend/docs/live_chula.png` et `frontend/docs/replay.png`).

## Ce que chaque agent a livré

| Agent | Livré | Chiffre clé |
|---|---|---|
| 1 VISION | `scripts/get_chula.sh`, `backend/vision/` (segmentation Otsu + watershed, mesures, validation), 3 échantillons `chula_264` (normal), `chula_246` (mixte), `chula_102` (riche en sphérocytes) avec overlay | AUC du SI sphérocytes contre normales : **0,963** [0,951 ; 0,974] sur 205 images tenues à l'écart |
| 2 PIPELINE | `backend/pipeline.py`, `backend/api/app.py` (toutes les routes de la section 6), NFS de démo, 2 échantillons synthétiques, `tests/test_pipeline.py` | D50 : 3,02 / 3,48 / 3,81 µm (normal / mixte / sphérocytes) ; route passage en 2 ms |
| 3 AGENT | `backend/agent/` (10 outils, orchestrateur, `number_guard`, prompt), `tests/test_agent.py`, `demo/replay_main.jsonl` et `demo/replay_guard.jsonl` | Rapport accepté : 59 nombres vérifiés, 0 non tracé |
| 4 FRONTEND | `frontend/` : écran unique, badges, 3D, courbes, trace, rapport, STL ; modes mock / live / replay (Shift+M, R, L, Espace, C, S) | Clic → 3D → passage animé en moins d'une seconde |
| 5 RED TEAM | `docs/redteam/` : critique des docs (v1), critique du produit (v2), `07_PITCH_FINAL.md` (415 mots, ≈ 2 min 46), `SLIDES.md`, `CHECKLIST.md` | 2 bloquants sur le produit (ci-dessous) |

## À décider ou à faire par Nolann

1. **Enregistrer les vrais replays (bloquant).** Les deux replays actuels sont des exécutions scriptées sur données synthétiques (sorties d'outils réelles, décisions écrites à l'avance), faute de clé API ici. Avec ta clé :
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   python -m backend.agent.orchestrator --record demo/replay_main.jsonl --samples chula_264 chula_102 --question "Would any subpopulation fail to pass narrow channels?"
   python -m backend.agent.orchestrator --record demo/replay_run2.jsonl --samples synthetic_healthy synthetic_hs --question "Compare both samples and propose a microfluidic test."
   python frontend/scripts/make_mocks.py   # recopie le replay dans le frontend
   ```
2. **Canal par défaut de la démo (bloquant).** À 3,00 µm, la cellule saine affichée par défaut sur `chula_264` est BLOCKED. Le script de démo de la red team règle le curseur à 3,30 µm (cellule A passe, cellule B bloquée à 4,9 %).
3. **Deux constantes de la physique à trancher**, car elles changent les chiffres montrés au jury :
   - `si_from_pallor` plafonne la pâleur à 0,40 : l'histogramme du SI d'un échantillon normal est un pic à 0,74, et la ligne « carence en fer » de `02` est impossible.
   - L'écart 3,02 contre 3,81 µm dépend surtout de `SI_SPHEROCYTE = 0,92`, non sourcé. Le pitch final ne cite plus l'écart en µm, seulement sa direction.
4. **Corriger `passage()` dans la physique** : au-delà du diamètre de la sphère de même volume, une cellule normale ressort BLOCKED (canal de 10 µm). L'API contourne le problème (`"unconfined": true`), pas le noyau.
5. **Libellé « 0 invented » → « 0 untraced »** dans le panneau rapport : le guard compare des chiffres, il ne vérifie pas le `tool_call_id`.
6. **Corriger `02`** (MCD 2,9–3,0 µm, ligne carence en fer) et ajouter la citation Chula RBC-12 (licence MIT) au README et à l'interface.

## Points d'environnement

- `npm install` dans le dossier partagé du projet ne termine pas (montage trop lent) ; sur les MacBook il est normal. `frontend/` n'a donc pas de `node_modules` ici.
- Cellpose est codé (voie A) mais n'a pas pu être testé ici (poids bloqués). Pour la démo : `CELLLAB_SEGMENTER=B`.
- Le dataset Chula cloné fait 350 Mo dans `external/` (ignoré par git).
