# CellLab — Pack de lancement pour Claude Project

> *Run experiments on cells before touching the cells.*

Ce dossier contient tout ce qu'il faut pour créer un Claude Project et lancer le développement de CellLab avec des agents.

## Installation (5 minutes)

1. **Crée un Project** sur claude.ai, nommé `CellLab — Hackathon`.
2. **Instructions du projet** : copie-colle tout le contenu de `01_INSTRUCTIONS_PROJET.md` dans le champ « Instructions » (custom instructions) du Project.
3. **Connaissances du projet** : uploade ces fichiers dans « Project knowledge » :
   - `02_CONTEXTE_SCIENTIFIQUE.md`
   - `03_ARCHITECTURE_ET_CONTRATS.md`
   - `04_AGENTS.md`
   - `06_PLAN_HEURE_PAR_HEURE.md`
   - `07_PITCH_ET_QUESTIONS_JURY.md`
   - `celllab_physics.py` (le cœur physique, déjà testé)
   - `passage_curve_demo.png` (le graphe de référence)
4. **Lancement** : ouvre une nouvelle conversation dans le Project et colle le prompt de `05_PROMPT_DE_LANCEMENT.md`.

## Trois façons de faire tourner les agents

| Mode | Quand l'utiliser | Comment |
|---|---|---|
| **A. Sous-agents dans une seule conversation** | Claude peut lancer des sous-agents dans ta session | Colle le prompt de lancement tel quel ; il demande de lancer les agents en parallèle. |
| **B. Une conversation par agent** | Équipe de 3-4 personnes, chacun son poste | Chaque personne ouvre une conversation dans le Project et colle le bloc « Brief » de son agent depuis `04_AGENTS.md`. |
| **C. Claude Code** | Vous codez dans un vrai repo | Mets `01_INSTRUCTIONS_PROJET.md` en `CLAUDE.md` à la racine du repo, les autres fichiers dans `docs/`, puis lance le prompt de lancement. |

Le mode B est le plus robuste en équipe : chacun avance en parallèle, et les **contrats JSON** de `03_ARCHITECTURE_ET_CONTRATS.md` garantissent que les morceaux s'emboîtent.

## Le cœur physique est déjà prêt

```bash
pip install numpy scipy matplotlib
python celllab_physics.py --selftest   # 19 tests, tous verts
python celllab_physics.py --demo       # graphe sain vs sphérocytose + proposition d'expérience
python celllab_physics.py --mesh       # STL ×5000 (≈4 cm) d'un discocyte et d'un sphérocyte
```

## Ordre des fichiers

| Fichier | Rôle |
|---|---|
| `01_INSTRUCTIONS_PROJET.md` | Règles permanentes : rôle, ton, règles de provenance, interdits |
| `02_CONTEXTE_SCIENTIFIQUE.md` | Biologie, physique S/V, formules, références, limites honnêtes |
| `03_ARCHITECTURE_ET_CONTRATS.md` | Repo, stack, schémas JSON entre modules, API, outils de l'agent |
| `04_AGENTS.md` | 5 briefs d'agents autonomes (mission, entrées, sorties, définition de « fini ») |
| `05_PROMPT_DE_LANCEMENT.md` | Le prompt à coller pour tout démarrer |
| `06_PLAN_HEURE_PAR_HEURE.md` | Plan sur 24 h avec points de contrôle et coupes de secours |
| `07_PITCH_ET_QUESTIONS_JURY.md` | Pitch de 3 min, script de démo, réponses aux questions difficiles |
| `exemples/` | Sorties de référence : deux STL ×5000 (discocyte et sphérocyte) et le résumé JSON de la démo, avec la proposition d'expérience. Pas besoin de les uploader dans le Project. |
