# CellLab — Pitch, script de démo et questions du jury

Le pitch et les réponses sont en anglais, prêts à être dits. Les chiffres entre crochets sont à remplacer par les vrais résultats du projet (l'agent 5 s'en charge).

## Pitch de 3 minutes

**[0:00 – 0:25] Le problème**
> A red blood cell is 8 microns wide, yet it squeezes through capillaries of 3 microns, millions of times in its life. When it loses that ability, the spleen destroys it, and patients become anemic. That happens in hereditary spherocytosis, in malaria, and even in donated blood as it ages in storage.
> Today, measuring this means microfluidic chips, micropipettes or optical tweezers. Slow, expensive, specialist labs. But every hospital already has a blood smear and a blood count.

**[0:25 – 0:45] L'idée**
> CellLab is a research agent that runs experiments on cells before anyone touches the cells. It turns a smear and a blood count into digital twins of every red cell, runs a virtual capillary experiment on the whole population, and tells you which real experiment is worth running.

**[0:45 – 2:15] Démo live**
1. *(échantillon A sain + échantillon B)* « Two samples. Here's the smear, here's the blood count. »
2. *(lancer l'agent, la trace défile)* « The agent plans first. It checks data quality, then cross-checks the image against the blood count: here it flags that sample B's RDW is consistent with what it sees on the smear. »
3. *(l'agent choisit un seuil et des largeurs)* « Now it decides on its own which channel widths to test and isolates a subpopulation: [31] % of sample B's cells are much more spherical. »
4. *(courbe de passage)* « This is the key result: the fraction of cells that pass versus channel diameter. Sample B needs [0.25] µm more to let half its cells through. »
5. *(clic sur la cellule « worst », animation)* « Here's one of those cells. Watch: the healthy one folds into the capillary with spare membrane. This one would need to stretch its membrane by more than 3 %, and red cell membranes rupture around 3 to 4 %. Blocked. »
6. *(badges)* « Every number on screen carries its provenance: measured from the image, constrained by the blood count, inferred by the model, or computed by physics. And our guard checks that the agent never invents a number: [0] unverified numbers in this report. »
7. *(carte d'expérience)* « Finally, it designs the real experiment: constriction widths of [2.8, 3.1, 3.3] µm, predicted pass rates, and only [17] cells per sample to see the effect. A hypothesis you can falsify tomorrow morning. »

**[2:15 – 2:45] Pourquoi c'est crédible**
> We don't predict stiffness from a photo: that would be fiction. We use geometry. A membrane that can't stretch, a volume that can't change: that alone sets a minimum channel diameter. Namvar et al. showed in 2021 that surface-to-volume ratio, not stiffness, is the main determinant of passage. Our model gives 3.0 µm for a normal cell, which matches their measurements.

**[2:45 – 3:00] La suite**
> Next: validate against real microfluidic data, and screen stored blood bags before transfusion. CellLab: run experiments on cells before touching the cells.

## Les 10 questions difficiles et nos réponses

**1. « How can you know a cell's mechanics from a 2D image? »**
> We don't, and we don't claim to. Our verdict is purely geometric: surface area and volume. Stiffness is only a hypothesis slider, labelled as such. That choice is backed by Namvar et al. 2021: surface-to-volume ratio, not viscoelasticity, is the major determinant of passage.

**2. « How do you get 3D volume and surface from a flat smear? »**
> Two sources. The blood count's MCV anchors the absolute volume of the population. The image gives relative size and shape. Surface is inferred from sphericity, which we estimate from central pallor, the same cue a hematologist uses to spot spherocytes. It's labelled INFERRED everywhere, and we validated it on annotated cells: AUC [x].

**3. « Isn't central pallor a crude proxy? »**
> Yes, it's our main assumption and we say so in every report. It's qualitatively standard in hematology. Quantitatively, the next step is calibrating it on quantitative phase or tomography data, where real 3D shapes exist.

**4. « Real capillaries aren't rigid tubes, and the spleen has slits. »**
> Correct. The capsule model is first-order, the classic Canham & Burton approach. It already reproduces the known 3 µm limit for normal cells. Slit geometry is a natural extension of the same surface/volume logic.

**5. « What about sickle cells? »**
> That's exactly where geometry isn't enough: sickle cells fail because of polymer rigidity. Our model says "geometrically possible" and the agent flags that rigidity must be tested. Knowing the limits of the model is a feature.

**6. « Why is this agentic and not just a pipeline? »**
> The agent decides what to do: it checks coherence between sources and reacts to incoherence, chooses which channel widths to sweep, which subpopulation to isolate, which cells to show, and designs the experiment. The physics tools are deterministic; the agent orchestrates them, and a guard rejects any number it didn't get from a tool.

**7. « Who is the user? »**
> Researchers in red cell biology, malaria labs and blood banks: people who run microfluidic experiments and want to know which ones are worth running. Not clinicians making a diagnosis.

**8. « Is this a medical device? »**
> No. It's a hypothesis-generation research tool. It never outputs a diagnosis.

**9. « Where does your data come from? »**
> Public annotated smears from the Chula RBC-12 dataset. Blood count values are demo values, clearly labelled. No patient data.

**10. « Why the 3D printed cell? »**
> It's a teaching prop at ×5000, so you can hold the difference between a healthy discocyte and a spherocyte. It's plastic, not biology, and we don't pretend otherwise.

## Script de secours

- **Le Wi-Fi tombe** : raccourci replay. Dire : « This is a run we recorded this morning, same code, same data. »
- **L'agent est lent** : parler de la courbe de passage pendant qu'il travaille ; elle est déjà calculée.
- **Tout plante** : vidéo de secours enregistrée entre H19 et H22.
