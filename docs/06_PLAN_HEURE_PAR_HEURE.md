# CellLab — Plan heure par heure (24 h)

Hypothèse : 24 h, équipe de 3 ou 4 personnes. Pour 36 ou 48 h, on garde les mêmes jalons et on étire les blocs « polish » ; on n'ajoute pas de fonctionnalités avant que le jalon 3 soit atteint.

## Rôles

| Personne | Rôle principal | Agents de dev qu'elle pilote |
|---|---|---|
| P1 | Agent + pitch (chef de projet) | Agent 3, Agent 5 |
| P2 | Frontend 3D | Agent 4 |
| P3 | Vision | Agent 1 |
| P4 (si 4 personnes) | Pipeline + API + intégration | Agent 2 |

Si vous êtes 3, P1 prend aussi le Pipeline : c'est léger, car la physique est déjà prête.

## Déroulé

| Heure | P1 — Agent / Pitch | P2 — Frontend | P3 — Vision | P4 — Pipeline / API |
|---|---|---|---|---|
| **H0 – H1** | Repo, clé API, lancement des agents, mocks synthétiques (Pipeline étapes 1 et 2) | Vite + React + r3f, mise en page vide avec mocks | Clone Chula RBC-12, licence, segmentation de repli (Otsu + watershed) | `build_population`, échantillons synthétiques |
| **H1 – H4** | `tools.py` (10 outils) testés sur les synthétiques | Maillage 3D depuis le JSON, capillaire, curseur D | `measure.py` : aire, diamètre, circularité, pâleur | API FastAPI : toutes les routes |
| **H4** | **JALON 1** : synthétiques de bout en bout. Courbe de passage et cellule 3D affichées depuis l'API | | | |
| **H4 – H8** | Orchestrateur + `number_guard`, première exécution complète | Animation du passage (morphing vers la capsule), panneau de trace | Cellpose si dispo, association aux annotations, validation pâleur → SI | Branche les 3 échantillons Chula, NFS de démo |
| **H8** | **JALON 2** : un échantillon Chula réel traverse tout ; l'agent rend un rapport avec 0 nombre non vérifié | | | |
| **H8 – H12** | Prompt de l'agent affiné, enregistrement de 2 replays | Rapport avec badges, carte d'expérience, comparaison côte à côte | Overlays propres, graphe de validation | STL ×5000, tests `pytest`, cache |
| **H12 – H16** | **Sommeil par rotation** (2 personnes dorment 3 h pendant que 2 travaillent, puis on inverse) | | | |
| **H16** | **JALON 3 : GEL DES FONCTIONNALITÉS.** Après ce point, on ne corrige que des bugs et de la lisibilité. | | | |
| **H16 – H19** | Red team (Agent 5), pitch avec les vrais chiffres | Lisibilité sur projecteur 1280×720, raccourci replay | Captures pour les slides | Intégration, bugs |
| **H19 – H22** | 3 répétitions chronométrées. **Enregistrement d'une vidéo de secours** de la démo | | | |
| **H22 – H24** | Marge. Batteries, adaptateurs HDMI, replay testé sans Wi-Fi | | | |

## Coupes de secours (décider sans débat au jalon)

| Si au jalon… | Alors on coupe… | Et on garde… |
|---|---|---|
| J1 : la 3D n'affiche rien | l'animation morphing | une cellule 3D statique et la courbe de passage (le graphe est le visuel le plus solide scientifiquement) |
| J1 : la segmentation ne marche pas | Cellpose | le repli Otsu + watershed, et sinon des cellules découpées à la main autour des annotations Chula |
| J2 : l'agent boucle ou invente des nombres | la liberté de l'agent | un agent avec 5 outils seulement et un plan imposé dans le prompt ; le `number_guard` reste |
| J2 : l'AUC pâleur → sphérocyte est faible | l'affirmation « on détecte les sphérocytes » | la démo sur les classes annotées (shape_class « annotation ») et l'honnêteté sur la limite |
| J3 : l'API live est instable | le mode live pendant le pitch | le **replay**, présenté honnêtement comme « une exécution enregistrée ce matin » |
| Partout : le temps manque | STL, comparaison côte à côte, sickle cells | le cœur : image → agent → courbe → cellule 3D → expérience proposée |

## Option impression 3D

Si une imprimante est disponible sur place (fablab, organisateurs), lancez l'impression du STL ×5000 (environ 4 cm) **avant H12**, car une impression de cette taille prend entre 30 et 90 minutes. Imprimez un discocyte et un sphérocyte : poser les deux sur la table pendant le pitch rend la différence de forme tangible.
