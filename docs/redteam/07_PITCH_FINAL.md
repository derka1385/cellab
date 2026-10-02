# CellLab : pitch final, script de démo et questions du jury

Copie complétée de `docs/07_PITCH_ET_QUESTIONS_JURY.md` (l'original n'est pas modifié). Le texte à dire est en anglais ; les consignes de scène sont en français, en italique. Chiffres mesurés le 2026-10-02 sur le repo (API locale, `backend/agent/tools.py`, `validation.json`).

Légende des chiffres :
- sans marque : chiffre réel, sorti du code ou de `validation.json`, stable (déterministe) ;
- **[live]** : chiffre que l'agent produira en direct ; la valeur indiquée est la sortie de l'outil pour ce choix (seuil SI > 0,85, cellule c112, largeurs proposées par `design_experiment`). À re-mesurer avec le run réel enregistré par Nolann : si l'agent choisit un autre seuil ou une autre cellule, dire le chiffre affiché à l'écran.

## Configuration de démo (impérative)

- URL : `http://localhost:5173/?mode=live&a=chula_264&b=chula_102` (par défaut, le frontend est en `mock` sur les synthétiques).
- Échantillons : A = `chula_264` (frottis normal), B = `chula_102` (riche en sphérocytes). Les deux sont de vraies images Chula RBC-12 ; les NFS sont des valeurs de démo.
- **Curseur du canal sur 3,30 µm avant de cliquer « Healthy vs test ».** À 3,00 µm (valeur par défaut), la cellule A choisie par défaut (c132, V 107 fL inféré) sort **BLOCKED** (3,4 % d'étirement). À 3,30 µm, A c132 PASSES et B c112 BLOCKED (4,9 % d'étirement). Voir `redteam_product_v2.md`, P2.
- Ne pas montrer la cellule « worst » de chula_102 (c040 : classe inconnue, V 189 fL, très probablement deux cellules collées). Montrer c112 (sphérocyte annoté, V 61 fL) ou c066 (sphérocyte annoté, V 77 fL).

## Pitch de 3 minutes

Mots prononcés : **415** (comptés par script sur les seules citations, nombres compris), soit **2 min 46 s à 150 mots/min**. Marge : 14 s pour les clics et l'attente de l'agent. À chronométrer à voix haute deux fois : à 165 mots/min (débit stressé), on tombe à 2 min 31 s.

**[0:00 – 0:25] Le problème** (68 mots)
> A red blood cell is about 8 microns wide, yet it squeezes through capillaries as narrow as about 3 microns, because it has spare membrane. Lose that spare membrane, and it can't fold any more: the spleen destroys it. That's hereditary spherocytosis, part of malaria, and probably stored blood. Measuring this takes microfluidic chips in specialist labs. But every hospital has a blood smear and a blood count.

**[0:25 – 0:40] L'idée** (41 mots)
> CellLab is a research agent that runs the experiment before anyone touches the cells. From a smear and a blood count, it builds a geometric twin of every red cell, sweeps virtual channels, and proposes the one real experiment worth running.

**[0:40 – 2:10] Démo live** (190 mots)
1. *(A et B déjà chargés)* « Two real smears from the public Chula RBC-12 dataset: A is normal, B is rich in spherocytes. The blood counts are demo values, and the screen says so. »
2. *(touche L : l'agent démarre, la trace défile)* « The agent plans, checks image quality, then cross-checks each smear against its blood count. Every line here is a call to a deterministic tool. »
3. *(message de seuil dans la trace)* « It isolates a subpopulation: **[live] 92 %** of B's cells have lost their central pallor, against **[live] 4 %** in A. »
4. *(courbe de passage)* « This is the key result: the fraction of cells that pass without stretching, versus channel diameter. Half of A passes at **3.02** microns; B needs **3.81**. »
5. *(curseur à 3,30, « Healthy vs test », « Simulate passage »)* « At 3.3 microns, A's cell folds in with membrane to spare. B's cell would have to stretch its membrane by **5 %**; membranes rupture at 3 to 4. Blocked, whatever its stiffness. »
6. *(badges, encart number_guard)* « Every number carries its source: measured, constrained by the blood count, inferred, or computed. A guard checks every number in the report against tool outputs: **[live] 59** checked, **[live] zero** untraced. »
7. *(carte d'expérience)* « Finally, the experiment: constrictions at **[live] 3.1, 3.3 and 3.6** microns. At 3.3, the model predicts **[live] 89 %** of A passes, and **[live] 10 %** of B. A hypothesis a lab can falsify tomorrow. »

*Si l'agent tourne encore à l'étape 4 : commenter la courbe (elle est calculée sans l'agent), puis revenir à la trace.*

**[2:10 – 2:45] Pourquoi c'est crédible** (72 mots)
> We don't predict stiffness from a photo. We use geometry: a membrane that can't stretch and a volume that can't change set a minimum channel diameter. Namvar and colleagues showed in 2021 that surface-to-volume ratio, not stiffness, drives passage. For the classic Evans–Fung cell, our model gives 3.02 microns; they measured 3.03 plus or minus 0.21 in healthy cells. Our weakest link is reading sphericity from central pallor, so we tested it.

**[2:45 – 3:00] Validation et suite** (44 mots)
> On 205 held-out images, pallor separates expert-labelled spherocytes from normal cells with an AUC of 0.96. That validates the detector, not the 3D shape. Next: calibrate on real 3D cell shapes and real microfluidic data. CellLab: run experiments on cells before touching the cells.

### Ce qui a changé par rapport au 07 du pack, et pourquoi

| Ligne du 07 | Devient | Raison |
|---|---|---|
| « capillaries of 3 microns, millions of times » | « as narrow as about 3 microns » | « millions » sans source (≈ 10⁵ estimé) ; sur le frottis normal, seules 45 % des cellules passent à 3,0 µm sans étirement. |
| « in malaria, and even in donated blood » | « part of malaria, and probably stored blood » | 02 dit « en partie » pour le paludisme ; la lésion de stockage n'est pas démontrée ici. |
| « it flags that sample B's RDW is consistent » | retiré de la démo | Sur Chula, les deux contrôles sortent COHERENT, et les NFS de démo ont été choisies pour coller à la morphologie : il n'y a rien à « découvrir ». Le cas INCOHERENT n'existe que sur `synthetic_hs`. |
| « It decides on its own which channel widths » | « proposes the one real experiment » | Les largeurs sortent d'un argmax déterministe ; l'agent choisit la plage, le seuil et les outils. |
| « [31] % of sample B's cells » | 92 % sur chula_102 (seuil 0,85) | Chiffre réel sur une vraie image, pas sur un synthétique (sur `synthetic_hs`, on a mis 30 % de sphérocytes : c'est un contrôle positif). |
| « needs [0.25] µm more » | D50 3,02 contre 3,81 µm | Chiffres réels. On ne dit **pas** « 0.8 µm more » : l'ampleur dépend de la constante SI_SPHEROCYTE = 0,92 (voir Q11). |
| « stretch by more than 3 % » | « by 5 % » à 3,3 µm (c112 : 4,9 %) | Valeur de l'API pour la cellule montrée. |
| « our guard checks that the agent never invents a number: [0] unverified » | « checks every number against tool outputs: 59 checked, zero untraced » | Le guard vérifie la traçabilité (2 chiffres significatifs), pas l'attribution. |
| « [2.8, 3.1, 3.3] µm … only [17] cells per sample » | 3,08 / 3,33 / 3,58 µm ; n non dit | `design_experiment(chula_264, chula_102)` donne n = 5 cellules par échantillon : techniquement correct, mais ouvre la question de la pseudo-réplication (Q7). On le garde pour les questions. |
| « Our model gives 3.0 µm for a normal cell, which matches their measurements » | « for the classic Evans–Fung cell, 3.02; they measured 3.03 ± 0.21 » | Avec la cellule moyenne de Namvar (V 99, S 149), le modèle donne 2,81 µm : « matches » ne tient pas. |
| AUC [x] | 0,96 (0,963 ; IC 95 % 0,951 à 0,974) | `validation.json`, images paires tenues à l'écart. |

## Script de démo minute par minute

| Temps | Écran | Action | Repli |
|---|---|---|---|
| Avant | Navigateur plein écran 1280×720, `?mode=live&a=chula_264&b=chula_102`, onglet B actif, curseur à 3,30 µm | Vérifier que la pastille LIVE est verte et que les deux D50 s'affichent | Si l'API ne répond pas : `?mode=replay` |
| 0:00 – 0:40 | Écran fixe (ou slide 1-2) | Parler | — |
| 0:40 | Panneau échantillons | Montrer A puis B (clic sur les onglets) | — |
| 0:50 | Trace | Touche **L** (run live) | Si erreur de clé ou réseau : touche **R** (replay) et dire la phrase de repli |
| 1:05 | Trace | Lire le message de seuil | — |
| 1:20 | Courbe de passage | Pointer D50 A et D50 B | La courbe ne dépend pas de l'agent |
| 1:35 | Vue 3D | « Healthy vs test », puis « Simulate passage » (Espace) | Si une cellule A sort BLOCKED : le curseur n'est pas à 3,30 |
| 1:50 | Rapport | Pointer les badges et l'encart number_guard | Si le rapport n'est pas encore là : touche **R** |
| 2:00 | Carte d'expérience | Lire les trois largeurs et les deux pourcentages à 3,3 | — |
| 2:10 – 3:00 | Écran fixe (slide 4) | Parler | — |

Temps d'exécution de l'agent :
- run scripté (`demo/replay_main.jsonl`, synthétiques) : **9,9 s** de bout en bout, dont **1,0 s** d'outils ; le reste est une latence simulée (1,2 s par tour, 7 tours). Ce n'est pas un temps de Claude.
- run live sur Chula : **à mesurer** par Nolann (cible : rapport affiché en moins de 60 s ; sinon lancer l'agent dès 0:40 et commenter la courbe pendant qu'il travaille).

## Les questions difficiles et nos réponses

Les questions 1 à 10 reprennent le 07 du pack, corrigées. Les questions 11 à 16 viennent du red team produit (`redteam_product_v2.md`).

**1. « How can you know a cell's mechanics from a 2D image? »**
> We don't, and we don't claim to. Our verdict is purely geometric: surface area and volume. Stiffness is only a hypothesis slider, labelled as such, and it never changes the verdict. That choice rests on Namvar et al. 2021: surface-to-volume ratio, not viscoelasticity, is the major determinant of passage.

**2. « How do you get 3D volume and surface from a flat smear? »**
> Two sources. The blood count's MCV anchors the absolute volume of the population. The image gives relative size and shape. Surface is inferred from sphericity, which we estimate from central pallor, the same cue a hematologist uses to spot spherocytes. It's labelled INFERRED everywhere. On 205 held-out Chula images, pallor separates expert-labelled spherocytes from normal cells with an AUC of 0.963, 95 % CI 0.951 to 0.974, and 0.953 on the 39 images that contain both kinds, which limits slide-to-slide effects.

**3. « Isn't central pallor a crude proxy? And your AUC is circular: annotators look at pallor. »**
> Yes to both, and we say so. The AUC shows our detector reproduces the expert's eye, not that our sphericity values are right: there is no 3D ground truth in Chula. It's also imperfect: 10 % of cells labelled normal score as spherical. The next step is calibrating on quantitative phase or tomography data, where real 3D shapes exist.

**4. « Real capillaries aren't rigid tubes, and the spleen has slits. »**
> Correct. The capsule model is first-order, after Canham and Burton: a geometric lower bound for a rigid cylinder. Below that bound the cylinder model simply doesn't apply, and slits need their own geometry, as in Pivkin et al. 2016. That's future work, not something we claim today.

**5. « What about sickle cells? »**
> That's exactly where geometry isn't enough: sickle cells fail because of polymer rigidity. Our verdict is necessary, not sufficient, and the experiment card says rigid cells may fail where geometry allows passage. Honest limit: our pallor rule was validated on round cells. Elongated cells are kept but misread: 31 % of annotated ovalocytes score as spherical. So today we would not analyse sickle smears without a shape filter.

**6. « Why is this agentic and not just a pipeline? »**
> The agent decides what to do: which quality and coherence checks to trust, which sphericity threshold isolates a subpopulation, which range of widths to sweep, which cells to show, and when to design the experiment. The physics tools are deterministic; the agent orchestrates them, and a guard refuses any report number that can't be traced to a tool output. We can show the refusal: in our guard test, the agent quoted a literature value, 149 square microns, that no tool produced; the report was rejected and resubmitted without it.

**7. « Five cells per sample? That's pseudo-replication. And which curve is your prediction? »**
> Five is the number of cells to count per sample to see this effect at 80 % power; it's a technical count. Biological replicates are donors, and you'd need several per group. The prediction is the no-stretch curve; the card also lists the fraction that passes under stretch, which is the lysis-risk zone.

**8. « Is this a medical device? »**
> No. It's a hypothesis-generation research tool. It never outputs a diagnosis, and the report says so.

**9. « Where does your data come from? »**
> Public, de-identified smears from the Chula RBC-12 dataset, MIT licence, Naruenatthanaset et al. 2021. The blood count values are demo values we chose to be plausible for each morphology, and they're labelled DEMO on screen. The agent's positive control uses synthetic populations, labelled SYNTHETIC.

**10. « Why the 3D printed cell? »**
> It's a teaching prop at 5000 times scale, about 4 cm, so you can hold the difference between a healthy discocyte and a spherocyte. It's plastic, not biology.

**11. « Your 0.8 micron gap is set by a constant you chose: spherocyte sphericity 0.92. »**
> Partly, yes. In sample B, most cells have no pallor at all, so they sit at our maximum sphericity of 0.92. With 0.85 instead, the typical B cell's minimum diameter drops from 3.9 to 3.4 microns. So the direction of the shift is robust and it's what we propose to test; its size is a model estimate. That's exactly why the output is an experiment, not a number to trust.

**12. « Your own model says half of the cells in the normal smear can't pass 3 microns without stretching. »**
> True: on that smear, 45 % pass at 3.0 microns without stretch, and the median minimum diameter is 3.02, right at the edge. Two reasons. Our diameter is a lower bound for a rigid tube, and real capillaries deform. And smear-based volumes are noisy, which widens the curve. That's why we compare A against B on the same model, rather than reading absolute pass rates.

**13. « Some of your cells have 20 or 190 femtolitre volumes. That's not a red cell. »**
> Correct, those are segmentation errors: two touching cells, or a fragment. Volume scales with area to the power 1.5, so any segmentation error is amplified. On our three smears, 3 to 12 % of cells fall outside 50 to 130 femtolitres; some are real microcytes, some are errors. They barely move the median, and we don't show them as examples. A plausibility filter is on our list.

**14. « The 'consistency' checks always say coherent. What do they catch? »**
> On these demo samples, nothing, and that's expected: we chose the demo blood counts to be plausible. On a synthetic sample with an inconsistent RDW, the agent flags it and explains why it continues anyway. The check is a signal, with a wide tolerance, not a diagnosis.

**15. « The replay: is that a real Claude run? »**
> *(Réponse uniquement si le replay scripté est encore celui du repo : sinon dire la phrase de repli ci-dessous.)* No: that file is a scripted dry run. The tool outputs are real, the decisions are scripted, and its first line says so. The live run uses the same tools.

**16. « Hereditary spherocytosis cells are small on a smear because they're thick, not because they've lost volume. Your area-to-volume rule underestimates them. »**
> Right: our volume rule assumes similar shapes, so it underestimates spherocyte volume. A bigger volume would raise their minimum diameter further, so the effect we show is, if anything, a lower bound.

## Script de secours

- **Le Wi-Fi tombe** : touche R (replay). Phrase à dire **seulement si Nolann a enregistré un vrai run** : « This is a run we recorded this morning, same code, same data. » Si le replay est encore le run scripté du repo : « This is a scripted dry run: the tool outputs are real, the agent's decisions are scripted. » Ne jamais présenter le run scripté comme un run de Claude.
- **L'agent est lent** : commenter la courbe de passage et la vue 3D, qui ne dépendent pas de l'agent.
- **Tout plante** : vidéo de secours (à enregistrer, voir `CHECKLIST.md`).
