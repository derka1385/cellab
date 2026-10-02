# CellLab : red team, phase 2 (critique du produit)

Date : 2026-10-02. Périmètre : ce qui tourne dans le repo, pas les intentions. Phase 1 : `redteam_docs_v1.md`.

**Ce qui a été vérifié et comment**
- Tests : `python3 -m pytest -q tests/` → **58 passed** (7 s).
- API locale (`127.0.0.1:8000`) interrogée avec `curl` : `/api/health`, `/api/samples`, `/api/samples/{id}`, `/passage` (d = 3 ; 3,3 ; 10 ; 20 ; 0,3), `/stl`, `/api/replay/{name}`.
- Outils de l'agent appelés directement sur la paire Chula de la démo (`backend/agent/tools.py` : `infer_geometry`, `find_subpopulation`, `sweep_channels`, `select_cells_for_display`, `design_experiment`). Ils sont déterministes : ce sont les chiffres que l'agent verra en live.
- Rapport de l'agent : `demo/replay_main.jsonl` et `demo/replay_guard.jsonl` lus en entier (événements, rapport, refus du guard).
- Interface : `frontend/src` (chaînes visibles), captures `frontend/docs/live_chula.png` et `replay.png`, logique de choix des cellules (`App.tsx`, `cellAtQuantile`).
- Validation : `backend/data/validation/validation.json` (y compris `per_class_all_annotations`).
- Sensibilité du MCD à la constante `SI_SPHEROCYTE` recalculée avec `celllab_physics.min_cylindrical_diameter`.
- STL : 4 fichiers contrôlés (arêtes, orientation, Euler, volume) par un script hors repo.
- Non vérifié ici : build du frontend (`node_modules` absent dans cet environnement), run live de Claude (pas de clé).

## 1. Chiffres réels retenus pour le pitch

| Grandeur | Valeur | Source |
|---|---|---|
| AUC SI sphérocyte contre normal | 0,963 (IC 95 % bootstrap par image : 0,951 à 0,974), 205 images tenues à l'écart, 2 738 normales et 1 625 sphérocytes | `validation.json` |
| AUC, images mixtes seulement | 0,953 (39 images, 1 050 normales, 706 sphérocytes) | idem |
| Cellules annotées normales avec SI > 0,85 | 10,1 % | idem |
| D50 chula_264 / chula_246 / chula_102 | 3,02 / 3,48 / 3,81 µm | `/api/samples` |
| D50 synthetic_healthy / synthetic_hs | 2,99 / 3,16 µm | idem |
| chula_102 : fraction SI > 0,85 | 92,3 % (96/104, dont 91 sphérocytes annotés) | `find_subpopulation` |
| chula_264 : fraction SI > 0,85 | 3,7 % | `infer_geometry` |
| Expérience chula_264 contre chula_102 | largeurs 3,08 / 3,33 / 3,58 µm ; à 3,33 : 89 % contre 9,6 % ; n = 5 cellules par échantillon | `design_experiment` |
| Cellule B montrée (c112) | V 61,5 fL, SI 0,92, MCD 3,60 µm ; 11,6 % d'étirement à 3,0 µm, 4,9 % à 3,3 µm | `/passage` |
| Temps de l'agent (run scripté) | 9,9 s, dont 1,0 s d'outils et 8,4 s de latence simulée (1,2 s × 7 tours) | `replay_main.jsonl` |
| Temps de l'agent (run live) | **à mesurer** | — |
| number_guard (run scripté) | 59 nombres vérifiés, 0 non tracé ; refus démontré sur « 149 » (`replay_guard.jsonl`) | idem |

## 2. Tableau des problèmes

Statut : **À CORRIGER** (action avant la démo), **CONTOURNÉ** (le script de démo l'évite), **ASSUMÉ** (dit au jury, réponse prête dans `07_PITCH_FINAL.md`), **RÉSOLU**.

| # | Gravité | Où | Constat vérifié | Attaque du jury | Correction proposée | Statut |
|---|---|---|---|---|---|---|
| P1 | BLOQUANT | `demo/replay_*.jsonl`, `frontend/public/mocks/replay_main.jsonl` ; script de secours du 07 du pack | Les deux replays sont des **runs scriptés** (décisions écrites à la main, sorties d'outils réelles) sur **données synthétiques**. L'étiquette n'est que dans le texte du PLAN, qui défile hors écran ; l'interface affiche seulement « REPLAY ». La phrase de secours du pack (« a run we recorded this morning ») serait fausse. Le replay ne correspond pas non plus à la démo Chula. | « Is that a real Claude run? » Si la réponse est « oui », c'est une fausse déclaration. | Nolann enregistre un vrai run sur la paire de démo : `python -m backend.agent.orchestrator --samples chula_264 chula_102 --record demo/replay_main.jsonl`, puis le copie dans `frontend/public/mocks/`. Idem pour un run de refus du guard. En attendant, phrase de secours honnête (dans le 07 final) ; FRONTEND : badge « SCRIPTED » si `mode == "scripted"` dans le premier événement. | À CORRIGER |
| P2 | BLOQUANT (démo) | `App.tsx` `cellAtQuantile(A, 0.5)` ; curseur par défaut 3,00 µm | En mode live Chula, la cellule A par défaut est **c132** (SI 0,74 mais V 107 fL inféré, MCD 3,13 µm). À 3,00 µm, l'API la donne **BLOCKED** (3,37 % d'étirement). Le « Healthy vs test » du pitch montrerait une cellule saine bloquée. | « Your healthy cell is blocked too. » | Script : curseur à **3,30 µm** (c132 PASSES, c112 BLOCKED à 4,9 %). FRONTEND : choisir A par MCD médian, ou prendre la cellule `typical` de l'agent (c097, MCD 2,93 µm, PASSES à 3 µm). | CONTOURNÉ |
| P3 | IMPORTANT | `select_cells_for_display(strategy="worst")` | Sur chula_102, la cellule « worst » est **c040** : classe inconnue, V **189 fL** (MCV 82), MCD 5,24 µm. C'est presque sûrement deux cellules collées. Le run scripté utilise la stratégie « worst » : un vrai run risque de faire pareil. | Hématologue : « A 189 fL red cell? » | AGENT : limiter « worst » aux cellules de V dans [p5 ; p95] ou de classe annotée connue. Script : montrer c112 ou c066 (sphérocytes annotés). | CONTOURNÉ (à corriger si temps) |
| P4 | IMPORTANT | `si_from_pallor`, `SI_SPHEROCYTE = 0.92` | L'ampleur de l'écart B contre A est **fixée par une constante** : dans chula_102, SI p10 0,881, médiane 0,92 = plafond. Avec 0,85 au lieu de 0,92, le MCD de la cellule B typique (V 77 fL) passe de 3,88 à 3,38 µm. L'écart des D50 (0,79 µm) n'est donc pas une mesure. 02 ne donne aucune source pour 0,92. | Biomécanique : « Your 0.8 µm is a parameter you chose. » | Dire « direction robuste, ampleur estimée » (Q11 du 07 final). Ne pas annoncer « 0.8 µm more » dans le pitch (fait). Ajouter une ligne de sensibilité dans le rapport ou les limitations. Sourcer 0,92 dans 02, ou le marquer HYPOTHESIS. | ASSUMÉ |
| P5 | IMPORTANT | Courbe de passage de chula_264 ; pitch « 3 µm capillaries » | Sur le frottis normal, **45 %** des cellules passent à 3,0 µm sans étirement (59,6 % BLOCKED à 2,85 µm). Le modèle dit donc que la moitié des cellules saines ne passe pas un capillaire de 3 µm sans étirement. | « Your model kills half of healthy cells. » | Pitch : « as narrow as about 3 microns ». Réponse Q12 : borne inférieure pour un tube rigide, volumes bruités, comparaison A contre B. | ASSUMÉ |
| P6 | IMPORTANT | `V_i = MCV × (A_i/médiane)^1,5` (pipeline) | Volumes inférés de **19,6 à 197 fL** ; hors [50 ; 130] fL : 2,8 % (chula_264), 12,4 % (chula_246), 7,7 % (chula_102). L'exposant 1,5 amplifie toute erreur de segmentation. Le biais de la phase 1 (#8) se voit aussi : la cellule B montrée fait 61,5 fL pour un MCV de 82. | Hématologue qui clique sur une cellule. | PIPELINE : drapeau `implausible_volume` hors [p2 ; p98] ou hors [40 ; 150] fL, exclu des exemples. Réponses Q13 et Q16. | ASSUMÉ |
| P7 | IMPORTANT | `cbc_consistency`, `data/samples/chula_*/cbc.json` | Sur les trois Chula, les deux contrôles sortent **COHERENT**, même quand le RDW impliqué par l'image (21 à 31 %) dépasse largement celui de la NFS (14 à 20,5 %) : la bande 0,6 à 1,6 est très large. Et les NFS de démo sont « chosen to be plausible for [the] morphology » : la cohérence est construite. En live sur Chula, l'agent n'aura **aucune incohérence** à laquelle réagir. | IA : « What does your agent actually decide? » | Pitch : retirer « flags that RDW is consistent » (fait). Q6 et Q14 prêtes. Option : une 3e NFS de démo volontairement incohérente pour montrer la réaction de l'agent, étiquetée comme telle. | ASSUMÉ |
| P8 | IMPORTANT | `ReportPanel.tsx` l. 31 | L'encart dit « **0 invented** ». Le guard ne prouve pas l'absence d'invention : correspondance à 2 chiffres significatifs, entiers 0, 1 et 2 ignorés, pas de contrôle de `tool_call_id` (phase 1, #14, non corrigé). Exemple : le seuil de lyse 0,03 est attribué à `tc_05` en COMPUTED parce que la constante figure dans `model_constants`. | IA : « Your guard accepts a number from A attributed to B. » | FRONTEND : « 0 untraced ». AGENT : vérifier que chaque `numbers[].value` se trouve dans la sortie de **son** `tool_call_id`. Pitch : « zero untraced » (fait). | À CORRIGER (libellé) / ASSUMÉ (fond) |
| P9 | IMPORTANT | `Charts.tsx` (histogramme SI) ; capture `live_chula.png` | Dans chula_264, **55 %** des cellules ont exactement SI 0,74 (pâleur ≥ 0,40 tronquée), ce qui fait une barre unique de ~70 % à l'écran sans explication. Les hypochromes (100 %), stomatocytes (100 %) et cellules cibles sont tous à 0,74. | Hématologue : « Your instrument saturates. » | FRONTEND : légende « ≤ 0.74: pallor ≥ 0.40, clipped » sur la barre. Retirer de 02 la ligne « carence en fer → oui ». | À CORRIGER |
| P10 | IMPORTANT | `validation.json`, `per_class_all_annotations` | Le SI lit à tort des formes non rondes comme sphériques : SI > 0,85 chez 31 % des ovalocytes, 39 % des schistocytes, 16 % des cellules cibles (pâleur nulle 15,7 %). La phase 1 craignait leur exclusion silencieuse ; en fait elles sont **gardées et mal lues** (aucune exclusion par circularité dans `segment.py`). | « Sickle cells? Ovalocytes? » | Q5 corrigée. VISION : drapeau de forme (circularité ou allongement) et SI non calculé pour les cellules allongées. | ASSUMÉ |
| P11 | IMPORTANT | AUC | L'AUC 0,963 reste partiellement circulaire (les annotateurs regardent la pâleur) ; 10 % des cellules normales ont SI > 0,85 ; une partie de l'écart peut venir de différences entre lames (0,953 sur images mixtes). Les caveats de `validation.json` le disent correctement. | « Circular validation. » | Pitch : « validates the detector, not the 3D shape » (fait). Q2 et Q3 prêtes. | ASSUMÉ |
| P12 | IMPORTANT | Temps de l'agent | Le seul temps disponible (9,9 s) est celui du run scripté, dont 85 % de latence simulée. Un run Claude réel à 14 appels d'outils peut prendre bien plus que les 90 s de démo. | Silence sur scène. | Nolann mesure 3 runs live sur la paire Chula. Si > 60 s : lancer l'agent dès 0:40, commenter la courbe (indépendante de l'agent). | À MESURER |
| P13 | IMPORTANT | `docs/02` §1, §2 | 02 n'a pas été corrigé depuis la phase 1 : « MCD 2,9 à 3,0 µm » (le code donne 2,85 à 3,11), « concorde avec Namvar », « carence en fer → oui ». 02 « fait foi » : un juré qui le lit voit des contradictions avec le produit. | — | Lead : appliquer les corrections #4, #5, #6 de la phase 1 dans 02. | À CORRIGER |
| P14 | IMPORTANT | `README.md`, `01` règle 5, interface | La licence MIT de Chula RBC-12 demande de garder la notice, et le README du dataset demande une citation (Naruenatthanaset et al. 2021) : elle n'apparaît **ni dans le README du repo, ni dans l'interface**. La règle 5 de 01 dit toujours « aucune donnée réelle de patient ». | « Whose data is this? » | README : section « Data » avec la citation et la licence. Slide 2 : citation (faite dans `SLIDES.md`). 01 : « frottis publics anonymisés ». | À CORRIGER |
| P15 | MINEUR | `design_experiment` | n = 5 cellules par échantillon pour la paire Chula (18 sur les synthétiques, le pitch du pack disait 17). Effectif technique, pas biologique. | Statistique : pseudo-réplication. | Q7 prête ; ne pas citer n dans le pitch (fait). | ASSUMÉ |
| P16 | MINEUR | Rapport scripté (`replay_main.jsonl`) | Le résumé dit « compatible with a spherocytic phenotype » pour un échantillon où l'on a planté 30 % de sphérocytes. Le contrôle positif marche (les 90 sphérocytes plantés sont tous dans la sous-population SI > 0,8, avec 27 cellules normales en plus, soit 39 %), mais le rapport ne le présente pas comme un contrôle. | « You found what you planted. » | Disparaît si P1 est corrigé (run sur Chula). Sinon, dire « positive control ». | ASSUMÉ |
| P17 | MINEUR | `View3DPanel.tsx` | « PASSES UNDER STRAIN » à 3 % = au seuil de lyse (phase 1, #19). « Stiffness changes speed only » : la vitesse de l'animation n'est pas une grandeur modélisée. | — | « PASSES AT LYSIS RISK » ; « Stiffness changes the animation speed only (not modelled) ». | À CORRIGER si temps |
| P18 | MINEUR | `ProvenanceBadge.tsx` ; `live_chula.png` | Le badge court de CONSTRAINED est « CBC » alors que la légende dit « CONSTRAINED ». À 1280×720, la ligne « RDW 18.5 % » est coupée à droite (badge invisible). | — | Badge « CONS » ou légende « CONSTRAINED (CBC) » ; réduire la ligne NFS. | À CORRIGER si temps |
| P19 | MINEUR | `frontend/src/lib/physics.ts` `passage()` (mode mock et repli) | Pas de plafonnement au diamètre de la sphère, contrairement à l'API. Une cellule de 40 fL (sphère 4,24 µm) peut sortir BLOCKED à 5 µm en mode mock. `celllab_physics.passage()` a toujours le défaut (phase 1, #3). | — | Même plafonnement que l'API dans `physics.ts` ; corriger la physique avec un test. | À CORRIGER si temps |
| P20 | MINEUR | `config.ts` | Mode par défaut `mock` et échantillons par défaut synthétiques : sans paramètres d'URL, la démo montre les synthétiques. | — | URL de démo fixée dans `CHECKLIST.md`. | CONTOURNÉ |

## 3. Suivi des points de la phase 1

| Phase 1 | État au 2026-10-02 |
|---|---|
| #1 unités en pixels étiquetées µm | **Résolu** : `area_um2` porte `unit: "px²"` et une note (l'API le montre). Le nom du champ reste trompeur. |
| #2 sous-population circulaire sur synthétiques | **Résolu dans le pitch** (démo sur Chula) ; reste dans le replay (P1, P16). |
| #3 BLOCKED dans un canal large | **Contourné** par l'API (`unconfined`) ; physique et `physics.ts` non corrigés (P19). |
| #4, #5 MCD 2,9-3,0 et « matches » Namvar | **Résolu dans le pitch** ; 02 non corrigé (P13). |
| #6 plancher SI 0,74 | Confirmé par la validation (hypochromes 100 % à 0,74) ; non affiché (P9). |
| #7 SI = pâleur recodée | Assumé (Q3). |
| #8 volume des sphérocytes sous-estimé | Confirmé sur données réelles (P6) ; assumé, biais conservateur (Q16). |
| #9 cellules non rondes | Pas exclues mais mal lues (P10). |
| #10 cellules saines bloquées à 3 µm | Confirmé, plus fort sur Chula (45 % passent, P5). |
| #12 AUC circulaire | Assumé (P11). |
| #13 « no patient data » | Corrigé dans le pitch ; README et 01 non corrigés (P14). |
| #14 guard | Libellé corrigé dans le pitch ; code et UI non corrigés (P8). |
| #15 n et pseudo-réplication | Assumé (P15). |
| #16 l'agent « choisit » les largeurs | Corrigé dans le pitch. |
| #17 « millions of times » | Retiré du pitch. |

## 4. Ce qui est solide (à dire sans crainte)

- 58 tests verts, selftest physique vert, API stable sur les cas limites (d hors bornes refusé en 422, identifiants encodés avec `..%2F` en 404).
- Provenance partout dans l'API (`Tagged` avec unité et note), y compris les D50.
- MCD d'Evans-Fung 3,02 µm ; Namvar 3,03 ± 0,21 µm (mesuré, cellules saines).
- Validation propre dans sa forme : seuil réglé sur les ids impairs, test sur les pairs, IC par bootstrap sur les images, contrôle sur images mixtes, caveats écrits.
- STL : maillages fermés et orientés (Euler 2, 0 arête non manifold), volumes cohérents avec V × 5000³ (discocyte 89,7 fL, c112 61,3 fL).
- Le refus du guard est démontrable (`replay_guard.jsonl` : « 149 » refusé, puis rapport accepté).
