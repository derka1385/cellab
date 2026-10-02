# CellLab — Prompt de lancement

Copie le bloc ci-dessous dans une nouvelle conversation du Claude Project. Avant d'envoyer, remplis les trois lignes entre crochets.

---

```
On lance CellLab. Tout le contexte est dans les fichiers du Project : lis 01 à 07 et celllab_physics.py avant d'agir.

INFOS ÉQUIPE
- Durée du hackathon : [ex. 24 h, de samedi 10 h à dimanche 10 h]
- Équipe : [ex. 3 personnes : Nolann (agent + pitch), X (frontend), Y (vision)]
- Machines : [ex. MacBook, pas de GPU, Python 3.11, Node 20]

CE QUE JE VEUX DE TOI MAINTENANT

1. Vérification express (5 min max)
   - Confirme en 5 lignes que tu as compris le projet, les contrats et les règles de provenance.
   - Signale tout ce qui te paraît incohérent entre les fichiers.

2. Lancement des agents
   - Si tu peux lancer des sous-agents : lance en parallèle les agents 1 (VISION), 2 (PIPELINE) et 4 (FRONTEND) avec leurs briefs exacts de 04_AGENTS.md. Lance l'agent 3 (AGENT) dès que l'agent 2 a livré les échantillons synthétiques. Lance l'agent 5 (PITCH & RED TEAM) en mode critique dès maintenant sur les documents, puis à nouveau en fin de parcours sur le produit.
   - Si tu ne peux pas lancer de sous-agents : dis-le, puis commence par l'agent 2 (étapes 1 et 2 seulement : mocks synthétiques), car il débloque tout le monde. Je collerai les autres briefs dans des conversations séparées.

3. Squelette du repo
   - Donne-moi le script bash complet qui crée l'arborescence de la section 3 de 03_ARCHITECTURE_ET_CONTRATS.md, copie celllab_physics.py dans backend/physics/, crée requirements.txt, le package.json du frontend, un .env.example (ANTHROPIC_API_KEY, CELLLAB_MODEL=claude-sonnet-5-5), un .gitignore, et un README de 20 lignes.
   - Donne l'ordre exact des commandes pour tout installer et vérifier (selftest de la physique, uvicorn, npm run dev).

4. Plan adapté
   - Adapte 06_PLAN_HEURE_PAR_HEURE.md à notre durée et à notre équipe : qui fait quoi, heure par heure, avec les points de contrôle et les coupes de secours.

FORMAT
- Fichiers complets et prêts à l'emploi, avec leur chemin. Pas de diffs.
- Code et interface en anglais, explications en français.
- À la fin : la liste des 3 prochaines actions de chaque membre de l'équipe.
```

---

## Prompts courts utiles pendant le hackathon

**Point de contrôle (toutes les 3 à 4 heures)**
```
Point de contrôle. Voici l'état : [colle la sortie des tests / ce qui marche / ce qui bloque]. Compare au plan de 06_PLAN_HEURE_PAR_HEURE.md. Dis-moi ce qu'on coupe, ce qu'on garde, et les 3 prochaines actions par personne.
```

**Débogage**
```
Bug dans [module]. Erreur complète : [colle]. Fichier concerné : [colle le fichier]. Donne le fichier corrigé complet, la cause en 2 lignes, et la commande pour vérifier.
```

**Red team avant la démo**
```
Joue le jury : un hématologue, une chercheuse en biomécanique des globules rouges et un expert en agents IA. Voici notre rapport d'agent et nos captures : [colle]. Pose les 8 questions les plus dures, puis donne notre meilleure réponse à chacune en 2 phrases, en t'appuyant uniquement sur 02_CONTEXTE_SCIENTIFIQUE.md.
```

**Intégration**
```
Le module [X] produit ceci : [colle un exemple JSON]. Le module [Y] attend le contrat [section]. Vérifie la conformité champ par champ et donne l'adaptateur complet si nécessaire.
```
