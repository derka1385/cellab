# CellLab : slides (5 maximum)

Texte prêt à mettre en forme, en anglais. Format 16:9, lisible à 1280×720 sur projecteur : 6 lignes au plus par slide, corps ≥ 28 pt. Les notes « Visuel » et « Dit à l'oral » sont en français, pour l'équipe. La slide 3 est remplacée par l'application en direct ; elle ne sert que si la démo tombe.

---

## Slide 1 : The problem

**Title:** Red cells live by folding

- A red cell is ~8 µm wide; capillaries can be ~3 µm.
- It fits because it has **spare membrane**.
- Lose that membrane → it can't fold → the spleen destroys it.
- Hereditary spherocytosis · part of malaria · probably stored blood.
- Measuring it today: microfluidic chips, micropipettes, specialist labs.

**Footer:** Every hospital already has a blood smear and a blood count.

*Visuel : un discocyte (biconcave) et un sphérocyte de même volume, côte à côte, devant un tube de 3 µm. On peut reprendre deux captures de la vue 3D. Montrer les deux cellules imprimées en 3D à ce moment.*

---

## Slide 2 : The idea

**Title:** Run the experiment before touching the cells

**Smear + blood count → geometric twin of every cell → virtual channel sweep → one falsifiable experiment**

- Image: relative size and central pallor (MEASURED)
- Blood count: absolute volume, MCV (CONSTRAINED)
- Surface and sphericity (INFERRED) · passage verdict (COMPUTED)
- An agent orchestrates deterministic tools; a guard traces every number to a tool output.

**Footer:** Data: Chula RBC-12, public de-identified smears (Naruenatthanaset et al., 2021, MIT licence). Blood counts are demo values.

*Visuel : schéma en 4 boîtes avec flèches ; les 5 couleurs de provenance de l'interface (vert, bleu, jaune, violet, rose).*

---

## Slide 3 : Live demo (slide de secours)

**Title:** Normal smear vs spherocyte-rich smear

| | A · normal (chula_264) | B · spherocyte-rich (chula_102) |
|---|---|---|
| Cells with no central pallor (SI > 0.85) | 4 % | 92 % |
| D50: half the cells pass, no stretch | **3.02 µm** | **3.81 µm** |
| Predicted pass rate at 3.3 µm | 89 % | 10 % |

- Proposed test: constrictions at 3.1, 3.3 and 3.6 µm.

**Footer:** Real smears, demo blood counts. Numbers: deterministic tool outputs; the live agent run may choose another threshold.

*Visuel : capture `frontend/docs/live_chula.png` refaite avec le curseur à 3,30 µm, plus la carte d'expérience. Dit à l'oral : « This is what the live run shows. » Si le replay scripté est affiché, le dire.*

---

## Slide 4 : Why trust it, and where it stops

**Title:** Geometry, validated where we can

- **Physics:** membrane can't stretch > 3–4 %, volume constant → minimum channel diameter (Canham & Burton).
- **Literature:** surface-to-volume, not stiffness, drives passage (Namvar et al., 2021). Evans–Fung cell: 3.02 µm in our model; Namvar measured 3.03 ± 0.21 µm.
- **Our weakest link, tested:** pallor separates expert-labelled spherocytes from normal cells, **AUC 0.96** (95 % CI 0.95–0.97), 205 held-out images.

**Limits:**
- AUC validates the detector, not 3D shape; 10 % of normal cells read as spherical.
- Size of the A/B gap depends on our assumed spherocyte sphericity; its direction is the claim to test.
- Rigid tubes, not real capillaries or spleen slits. No stiffness. Not a diagnosis.

*Visuel : `backend/data/validation/pallor_validation.png` à droite. Cette slide a 9 lignes : la couper en deux colonnes (preuves à gauche, limites à droite).*

---

## Slide 5 : Next

**Title:** From hypothesis to bench

- Calibrate sphericity on real 3D shapes (quantitative phase, tomography).
- Test the predicted pass curves on microfluidic constrictions, with several donors.
- Slit geometry for the spleen.
- Screen stored blood bags before transfusion.

**Footer:** CellLab: run experiments on cells before touching the cells. · Research tool, not a medical device.

*Visuel : la carte d'expérience de l'interface ; logo ; lien du repo.*
