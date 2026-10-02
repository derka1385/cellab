# CellLab — Contexte scientifique

Ce document fait foi pour toute affirmation biologique ou physique du projet. Si une affirmation du code, de l'interface ou du pitch n'est pas couverte ici, elle doit être vérifiée avant d'être montrée au jury.

## 1. Le problème biologique

Un globule rouge humain (érythrocyte) mesure environ 7,5 à 8 µm de diamètre. Pourtant, il traverse des capillaires d'environ 3 µm et des fentes de la rate encore plus étroites. Il y parvient parce qu'il a **plus de membrane qu'il n'en faut pour envelopper son volume** : sa forme biconcave lui donne une réserve de surface.

Quand cette réserve disparaît, la cellule ne passe plus. La rate la retient et la détruit, ce qui provoque une anémie hémolytique. Plusieurs situations font perdre cette réserve :

| Situation | Ce qui change | Ce que notre modèle capture |
|---|---|---|
| Sphérocytose héréditaire | Perte de membrane, la cellule devient plus sphérique | Oui : S baisse, l'indice de sphéricité monte, le diamètre minimal de passage augmente |
| Lésion de stockage des poches de sang | Perte de membrane par microvésiculation au fil des semaines | Oui, même mécanisme géométrique (piste d'application forte) |
| Paludisme (*P. falciparum*) | Baisse du rapport S/V des globules infectés | Oui en partie (Namvar et al. 2021) |
| Drépanocytose | Polymérisation de l'HbS, la cellule devient **rigide** et déshydratée | **Non suffisant** : le verdict géométrique est nécessaire mais pas suffisant. On le signale. |
| Carence en fer (microcytes hypochromes) | Cellules petites et fines, souvent avec plus de réserve de surface | Oui (sphéricité plus basse) |

Aujourd'hui, on mesure la déformabilité avec de la microfluidique, des micropipettes, des pinces optiques, l'AFM ou l'ektacytométrie. Ce sont des méthodes lentes, coûteuses et peu accessibles. Le frottis sanguin et la NFS, eux, sont partout.

## 2. Le cœur physique : la géométrie suffit pour une première réponse

### Deux faits établis

1. **La membrane ne s'étire presque pas en surface.** Elle se rompt (lyse) après environ 3 à 4 % d'augmentation d'aire (Evans, Waugh & Melnik, 1976). Le code utilise 3 % (`LYSIS_AREA_STRAIN`), une valeur prudente.
2. **Le volume est quasi constant** pendant un passage rapide : l'eau n'a pas le temps de sortir.

Conséquence : avec une surface S et un volume V fixés, il existe un **diamètre cylindrique minimal (MCD, minimum cylindrical diameter)** en dessous duquel la cellule ne peut pas passer, quelle que soit sa souplesse (Canham & Burton, 1968).

### Le modèle « capsule »

Dans un tube de diamètre D, on modélise la cellule comme un cylindre de rayon R = D/2 fermé par deux hémisphères. Pour un volume V donné, la surface nécessaire est :

```
S_required(D) = 4V/D + (π/3)·D²
```

- Si `S ≥ S_required(D)` : **PASSES** (la cellule a assez de membrane).
- Si `S < S_required(D) ≤ 1,03·S` : **PASSES_UNDER_STRAIN** (passage au prix d'un étirement de la membrane, proche de la lyse).
- Sinon : **BLOCKED**.

Le MCD est la racine de `S_required(D) = S` pour D inférieur au diamètre de la sphère de même volume. Pour une cellule normale (V ≈ 90 à 94 fL, S ≈ 131 à 135 µm²), on obtient un **MCD ≈ 2,9 à 3,0 µm**, ce qui concorde avec la littérature (Namvar et al. 2021 rapportent un MCD moyen de 3,03 ± 0,21 µm sur des cellules saines).

### L'indice de sphéricité

```
SI = (36π)^(1/3) · V^(2/3) / S   ≈ 4,836 · V^(2/3) / S
```

Il vaut 1 pour une sphère et environ 0,74 pour le discocyte moyen d'Evans & Fung. Plus il est élevé, moins la cellule a de réserve.

### Le résultat qui fonde le projet

Namvar et al. (2021) ont montré expérimentalement que **le rapport surface/volume, et non la viscoélasticité, est le déterminant principal** du passage des globules rouges dans des microcanaux. Leur titre dit littéralement : *« Surface area-to-volume ratio, not cellular viscoelasticity, is the major determinant of red blood cell traversal through small channels. »*

C'est notre meilleure réponse à la question « pourquoi ne pas prédire la rigidité ? ».

## 3. De l'image et de la NFS au jumeau numérique

C'est ici qu'on infère des choses. Chaque étape est étiquetée.

| Grandeur | Source | Étiquette | Méthode |
|---|---|---|---|
| Aire projetée, diamètre, circularité | Image | MEASURED | Segmentation (Cellpose ou seuillage + watershed) |
| Rapport de pâleur centrale (diamètre de la zone pâle / diamètre de la cellule) | Image | MEASURED | Profil d'intensité dans le masque |
| Volume moyen de la population | NFS : VGM (MCV) | CONSTRAINED | Ancrage de l'échelle absolue |
| Volume par cellule V_i | Image + NFS | INFERRED | `V_i = MCV × (A_i / médiane(A))^1,5`, normalisé pour que la moyenne soit exactement le MCV |
| Sphéricité par cellule SI_i | Image | INFERRED | Interpolation linéaire selon la pâleur : pâleur normale (≈ 0,40) donne SI ≈ 0,74, pâleur absente donne SI ≈ 0,92 |
| Surface par cellule S_i | Calcul | INFERRED | `S_i = 4,836 · V_i^(2/3) / SI_i` |
| MCD, verdict, courbe de population | Physique | COMPUTED | Modèle capsule |
| Rigidité | Utilisateur ou agent | HYPOTHESIS | Curseur explicite, jamais mélangé au verdict |

**Pourquoi la NFS fixe l'échelle :** un frottis séché s'aplatit et se déforme, donc les diamètres absolus y sont peu fiables. L'image donne les tailles **relatives** et la **forme** ; la NFS donne l'échelle **absolue**. Conséquence pratique : on n'a même pas besoin de connaître la taille du pixel en µm pour calculer V et S.

**L'hypothèse principale du pipeline** est la relation entre pâleur centrale et sphéricité. Elle est qualitativement solide (un sphérocyte n'a pas de pâleur centrale, c'est un critère classique de lecture de frottis) mais quantitativement approximative. On la valide sur le dataset annoté Chula RBC-12 (section 6) et on le dit pendant le pitch.

### Contrôles de cohérence entre l'image et la NFS (le côté agentique)

- **RDW et diamètre** : puisque V ∝ D³, on a approximativement CV(V) ≈ 3 × CV(D). On compare le RDW-CV de la NFS (normal : 11,5 à 14,5 %) à trois fois le coefficient de variation des diamètres mesurés. Un écart important signale un frottis non représentatif ou une sous-population.
- **CCMH (MCHC) et pâleur** : une CCMH haute (> 36 g/dL) accompagnée de nombreuses cellules sans pâleur forme un tableau cohérent (cellules denses et sphériques). Une CCMH haute avec une pâleur normale partout est incohérente et doit être signalée.

Ce sont des **signaux**, pas des diagnostics.

## 4. La 3D : visualisation contrainte, pas simulation mécanique

- **Forme au repos** : profil d'Evans & Fung (1972), avec une épaisseur totale `T(x) = √(1−x²)·(0,81 + 7,83x² − 4,39x⁴)` µm, R₀ = 3,91 µm. On le transforme (paramètre `morph_t`) vers une sphère pour atteindre la sphéricité inférée, puis on l'ajuste au volume. Le code vérifie que V et SI sont respectés.
- **Forme dans le capillaire** : une capsule de rayon D/2 et de volume V (`capsule_shape`). L'animation interpole entre la forme au repos et la capsule. Elle est **contrainte par la géométrie** (V conservé, S comparé à S_required) mais ne résout aucune équation de mécanique. On le dit.
- **Couleur de la membrane pendant le passage** : l'étirement de surface nécessaire (`area_strain_needed`), de 0 % (vert) à 3 % (rouge, lyse).

## 5. Ce qu'on ne prétend pas (à dire avant que le jury le demande)

1. Une photo 2D ne donne pas les propriétés mécaniques. On ne les prédit pas.
2. La sphéricité est **inférée** de la pâleur centrale ; c'est une approximation, validée seulement sur un dataset annoté.
3. Les vrais capillaires ne sont pas des tubes rigides, et les fentes de la rate ne sont pas des cylindres. Le modèle capsule est un **premier ordre** défendable, pas une vérité.
4. Pour les cellules rigides (drépanocytes), le verdict géométrique est nécessaire mais pas suffisant.
5. CellLab est un outil de **génération d'hypothèses** pour la recherche, pas un dispositif médical.

## 6. Données

| Dataset | Contenu | Usage dans CellLab |
|---|---|---|
| **Chula RBC-12** | 706 images de frottis (640×480), plus de 20 000 globules rouges annotés par un point (x, y) et une classe parmi 12 morphologies, dont normal, sphérocyte, cellule cible, stomatocyte, ovalocyte, elliptocyte, schistocyte | **Dataset principal.** Segmentation, mesures, et validation de l'inférence pâleur → sphéricité (les sphérocytes annotés doivent ressortir avec un SI plus élevé). |
| **erythrocytesIDB** (Université des îles Baléares) | Images de frottis de patients drépanocytaires, cellules circulaires, allongées et autres | Optionnel : montrer le cas où la géométrie ne suffit pas. |
| Acevedo (PBC dataset) | 17 092 images, surtout des globules blancs | **Pas adapté** à CellLab (pas de morphologie érythrocytaire anormale). |

Vérifier la licence et le téléchargement de chaque dataset dans la première heure. Les NFS associées aux images sont des **valeurs de démo**, étiquetées comme telles.

## 7. Valeurs de référence

| Grandeur | Valeur | Remarque |
|---|---|---|
| Diamètre d'un globule rouge | 7,5 à 8 µm | Sur frottis, varie avec la préparation |
| Volume (VGM, MCV) | 80 à 100 fL | Evans & Fung moyen : ≈ 94 fL |
| Surface | 130 à 150 µm² | Evans & Fung : ≈ 134 µm² ; Namvar : 149 ± 14 µm² |
| Indice de sphéricité normal | ≈ 0,73 à 0,75 | 1 pour une sphère |
| MCD normal | ≈ 2,8 à 3,0 µm | Namvar 2021 : 3,03 ± 0,21 µm |
| Étirement de surface avant lyse | ≈ 3 à 4 % | Le code utilise 3 % |
| RDW-CV normal | 11,5 à 14,5 % | |
| CCMH (MCHC) normale | 32 à 36 g/dL | Souvent > 36 dans la sphérocytose héréditaire |

## 8. Références

- Canham PB, Burton AC. *Distribution of size and shape in populations of normal human red cells.* Circulation Research, 1968. https://circres.ahajournals.org/content/circresaha/22/3/405.full.pdf
- Evans E, Fung YC. *Improved measurements of the erythrocyte geometry.* Microvascular Research, 1972. (Profil biconcave utilisé pour la 3D.)
- Evans EA, Waugh R, Melnik L. *Elastic area compressibility modulus of red cell membrane.* Biophysical Journal, 1976. (Lyse vers 3 à 4 % d'étirement de surface.)
- Namvar A et al. *Surface area-to-volume ratio, not cellular viscoelasticity, is the major determinant of red blood cell traversal through small channels.* Cellular Microbiology, 2021. https://pmc.ncbi.nlm.nih.gov/articles/PMC7757199/
- Pivkin IV et al. *Biomechanics of red blood cells in human spleen and consequences for physiology and disease.* PNAS, 2016. https://www.pnas.org/doi/10.1073/pnas.1606751113
- *Physical mechanisms of red blood cell splenic filtration.* PNAS, 2023. https://www.pnas.org/doi/10.1073/pnas.2300095120
- Chula RBC-12 Dataset. https://github.com/Chula-PIC-Lab/Chula-RBC-12-Dataset
- erythrocytesIDB. https://erythrocytesidb.uib.es/
