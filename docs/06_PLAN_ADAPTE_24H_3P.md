# CellLab — Plan adapté : 24 h, 3 personnes

Hypothèses retenues (les valeurs d'exemple du prompt, à corriger si besoin) : samedi 10 h → dimanche 10 h, 3 personnes, MacBook sans GPU, Python 3.11, Node 20.

| Personne | Rôle | Pilote | Possède dans le repo |
|---|---|---|---|
| **Nolann** | Agent + pitch + pipeline/API + intégration (chef de projet) | Agents 2, 3, 5 | `backend/pipeline.py`, `backend/api/`, `backend/agent/`, `demo/`, `docs/` |
| **X** | Frontend 3D | Agent 4 | `frontend/` |
| **Y** | Vision + validation, puis captures et slides | Agent 1 | `backend/vision/`, `scripts/get_chula.sh`, `backend/data/samples/chula_*` |

Pourquoi Nolann prend le pipeline : la physique est déjà prête, le pipeline est léger, et une première version des mocks et de l'API est déjà en cours de génération. Nolann ne code pas l'API de zéro, il la relit, la teste et la branche.

Règle de contrats : toute modification d'un schéma de `03_ARCHITECTURE_ET_CONTRATS.md` est annoncée dans le canal de l'équipe **avant** d'être codée. Nolann arbitre.

## Déroulé

| Heure | Nolann (agent / pipeline / pitch) | X (frontend) | Y (vision) |
|---|---|---|---|
| **Sam 10:00 – 11:00 (H0–H1)** | Repo cloné, `.env` avec la clé, selftest vert, `pytest` vert. Vérifie que `backend/data/samples/synthetic_*` existent et que `uvicorn` démarre. Poste dans le canal : « mocks OK ». | `npm install`, `npm run dev` affiche l'écran avec les mocks. Relit le composant `ProvenanceBadge` et la mise en page sur 1280×720. | `scripts/get_chula.sh`, licence vérifiée. Segmentation de repli (Otsu + watershed) sur 5 images, overlay regardé à l'œil. |
| **11:00 – 14:00 (H1–H4)** | `backend/agent/tools.py` : les 10 outils, testés un par un sur `synthetic_healthy` et `synthetic_hs` (résultats < 1 500 caractères). | Maillage 3D depuis `/mesh`, tube capillaire, curseur D branché sur `/passage` (< 50 ms). | `measure.py` : aire, diamètre, circularité, pâleur, exclusions. Association aux annotations Chula. |
| **14:00 — JALON 1** | **Synthétiques de bout en bout : courbe de passage et cellule 3D affichées depuis l'API (pas depuis les mocks).** Point de 15 min à trois, décision des coupes. | | |
| **14:00 – 18:00 (H4–H8)** | Orchestrateur + `number_guard`, première exécution complète sur synthétiques (< 60 s, 0 nombre non vérifié). | Animation du passage (morphing vers la capsule, couleur selon l'étirement), panneau de trace (live + replay). | `validate_pallor.py` sur ≥ 50 images → `validation.json` + PNG. 3 échantillons de démo avec overlay. Cellpose seulement si le repli est insuffisant **et** que l'installation passe en < 20 min. |
| **18:00 — JALON 2** | **Un échantillon Chula réel traverse tout ; l'agent rend un rapport avec 0 nombre non vérifié.** Nolann écrit les `cbc.json` de démo des 3 échantillons Chula. | | |
| **18:00 – 22:00 (H8–H12)** | Prompt de l'agent affiné, **2 replays enregistrés** (`demo/replay_main.jsonl` + un second). Lance l'agent 5 en red team sur le produit. | Rapport avec badges, carte d'expérience, comparaison côte à côte, bouton STL. | Overlays propres, graphe de validation lisible, puis aide à l'intégration (bugs vision côté API). Impression 3D lancée **avant 22:00** si une imprimante existe. |
| **22:00 – 04:00 (H12–H18)** | **Sommeil en rotation, 3 créneaux de 3 h, 2 personnes éveillées à chaque fois :** | | |
| 22:00 – 01:00 | éveillé : intégration, bugs | **dort** | éveillé : captures, aide frontend |
| 01:00 – 04:00 | **dort** | éveillé : lisibilité, raccourci replay | éveillé : relit les chiffres du rapport |
| 04:00 – 07:00 | éveillé : pitch avec vrais chiffres | éveillé : polish | **dort** |
| **02:00 — JALON 3 : GEL DES FONCTIONNALITÉS** | Après ce point, uniquement bugs et lisibilité. Celui qui est éveillé l'annonce dans le canal. | | |
| **04:00 – 07:00 (H18–H21)** | Red team (agent 5) sur le produit, `07` complété avec les vrais chiffres (AUC, D50, durée de l'agent), 5 slides. | Test 1280×720, textes ≥ 16 px, replay au clavier sans réseau. | (dort jusqu'à 07:00) |
| **07:00 – 09:00 (H21–H23)** | 3 répétitions chronométrées (< 3 min). **Vidéo de secours** de la démo enregistrée. | Corrige ce que les répétitions révèlent. | Chronomètre, joue le jury (questions de `07`). |
| **09:00 – 10:00 (H23–H24)** | Marge. Batteries, HDMI, replay testé Wi-Fi coupé, checklist de l'agent 5 cochée. | | |

Le jalon 3 est avancé à H16 (02:00) comme dans le plan d'origine, mais tombe pendant la rotation de sommeil : c'est volontaire, personne ne doit lancer une nouvelle fonctionnalité la nuit.

## Points de contrôle

À chaque jalon, Nolann colle dans Claude le prompt « Point de contrôle » de `05_PROMPT_DE_LANCEMENT.md` avec la sortie de :

```bash
python backend/physics/celllab_physics.py --selftest | tail -1
pytest -q
curl -s localhost:8000/api/samples | head -c 300
```

## Coupes de secours (décider sans débat au jalon)

| Si au jalon… | Qui décide | Alors on coupe… | Et on garde… |
|---|---|---|---|
| J1 : la 3D n'affiche rien | X propose, Nolann tranche | l'animation morphing | une cellule 3D statique + la courbe de passage |
| J1 : la segmentation ne marche pas | Y | Cellpose | Otsu + watershed, sinon des cellules découpées autour des annotations Chula |
| J1 : l'API n'est pas branchée | Nolann | le live côté frontend | le frontend sur les fichiers `population.json` statiques (repli de la stack) |
| J2 : l'agent boucle ou invente des nombres | Nolann | la liberté de l'agent | 5 outils, plan imposé dans le prompt, `number_guard` conservé |
| J2 : AUC pâleur → sphérocyte < 0,7 | Y + Nolann | « on détecte les sphérocytes » | la démo sur les classes annotées et l'honnêteté sur la limite |
| J3 : l'API live est instable | Nolann | le live pendant le pitch | le replay, « exécution enregistrée ce matin » |
| Partout : le temps manque | Nolann | STL, côte à côte, drépanocytes | image → agent → courbe → cellule 3D → expérience proposée |

Avec 3 personnes, la coupe la plus probable est **Cellpose** (installation de PyTorch sur Mac sans GPU, gain incertain) : on part directement sur le repli.

## Risque à vérifier avant samedi 10 h

Une partie du code est générée **avant** le début du hackathon (mocks, API, frontend, vision). Vérifiez dans le règlement que le code préparé à l'avance est autorisé. Si ce n'est pas le cas, gardez seulement `celllab_physics.py` (déjà dans le pack) et les docs, et utilisez le code généré comme référence à reproduire pendant l'événement.
