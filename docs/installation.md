# L'installation : `install.py`

`install.py` installe Hermes, le met à jour, et règle le pare-feu du serveur. Il se lance **sur le serveur Linux**,
depuis le dossier du dépôt, avec le Python du système (aucune dépendance à installer) :

```bash
python3 install.py              # installer ou mettre à jour
python3 install.py --help       # la liste des options
```

Chaque ligne qu'il affiche commence par `OK`, `ÉCHEC` ou `ATTENTION`. Il ne montre jamais un secret, ne le passe
jamais en ligne de commande, et crée le `.env` lisible par son seul propriétaire.

## Les options

| Commande | Ce qu'elle fait | Quand l'utiliser |
|---|---|---|
| `python3 install.py` | Installe Hermes, ou le met à jour : vérifications, `.env`, démarrage, réglages | La première fois, puis après chaque `git pull` |
| `python3 install.py --reconfigurer` | Repose toutes les questions du `.env` (les valeurs existantes sont proposées), puis installe | Pour changer un mot de passe, une clé de modèle, Telegram ou un plafond de ressources |
| `python3 install.py --pare-feu` | Met en place le pare-feu de tout le serveur, sans question | Une fois, puis après l'ajout d'un conteneur qui publie des ports (voir [pare-feu-serveur.md](pare-feu-serveur.md)) |
| `python3 install.py --vault` | Relie Hermes au vault : il y dépose des notes et transmet tes autres demandes à Claude Code (tri, commit…), sans question | Une fois le vault installé sur le serveur, puis si le réseau Docker de Hermes change (voir [lien-vault.md](lien-vault.md)) |

## Ce que fait `python3 install.py`, étape par étape

1. **Les vérifications** : Linux, Docker, Docker Compose v2, démon Docker joignable, ports de Hermes libres (sauf si
   Hermes tourne déjà), mémoire disponible face au plafond choisi.
2. **Le `.env`** :
   - **absent** : il est créé depuis `.env.example`, en posant les questions. L'UID et le GID sont lus sur la machine ;
     la clé de la Gateway API (`API_SERVER_KEY`) et la clé de session du Dashboard
     (`HERMES_DASHBOARD_BASIC_AUTH_SECRET`) sont tirées au hasard ; le mot de passe du Dashboard, les clés des
     modèles et le jeton Telegram sont demandés sans être affichés ; les identifiants Telegram autorisés et les
     plafonds de ressources sont demandés.
   - **présent** : il n'est **jamais réécrit**. Seules les variables apparues dans `.env.example` depuis la dernière
     fois sont ajoutées à la fin, après une copie de sauvegarde `.env.bak` : une clé tirée au hasard pour les clés
     générées, une question pour les autres secrets, la valeur d'exemple pour le reste.
3. **Le démarrage** : `docker compose config` (le fichier est valide), `docker compose up -d`, puis l'attente du
   Dashboard et le contrôle qu'il exige une connexion (`/api/status`).
4. **Les réglages** : chaque ligne de `reglages.conf` est appliquée avec `hermes config set`, puis Hermes redémarre
   (voir « Les verrous » ci-dessous).
5. **Le modèle**, à la première installation seulement : il propose l'assistant de Hermes, `hermes model`, pour
   choisir le fournisseur et le modèle.

## Les verrous : `reglages.conf`

Les verrous sont les réglages qui empêchent Hermes d'agir seul. Ils vivent dans `reglages.conf`, versionné, et sont
appliqués à chaque passage d'`install.py` par `hermes config set`, une valeur à la fois : `data/config.yaml`, qui
appartient à Hermes et change d'une version à l'autre, n'est jamais réécrit.

| Réglage | Valeur | Ce qu'il empêche |
|---|---|---|
| `approvals.mode` | `manual` | Hermes demande ton accord avant toute commande qu'il juge dangereuse, au lieu de laisser un modèle juger (`smart`) |
| `memory.nudge_interval` | `0` | Il ne retient rien de lui-même : seulement à ta demande |
| `skills.creation_nudge_interval` | `0` | Il ne crée aucun skill de lui-même : seulement à ta demande. À 0, ces deux rappels arrêtent aussi la relecture automatique en arrière-plan (`background_review`), qui écrit mémoire et skills |

**Répondre à une demande d'approbation** (Telegram, Dashboard, terminal) :

| Réponse | Effet |
|---|---|
| Refuser | La commande ne s'exécute pas |
| Une fois | Seulement cette fois : la réponse à privilégier |
| Pour la session | Plus redemandé jusqu'à la fin de la conversation en cours |
| Toujours | À éviter : la commande entre dans une liste permanente et ne sera plus jamais redemandée ; le verrou se vide |

**Limite connue** : Hermes peut lui-même changer ces réglages (`hermes config set`), puisqu'il a accès à son
terminal ; repasser `install.py` les rétablit (voir l'issue NousResearch/hermes-agent#104059).

Ajouter un verrou : une ligne `clé valeur` dans `reglages.conf`, puis `python3 install.py`.

## Mettre à jour

```bash
git pull && python3 install.py
```

Rien n'est perdu : le `.env` est complété sans être réécrit, et les données de Hermes (mémoire, sessions, skills,
configuration) vivent dans `data/`, un dossier du serveur, qui survit à tout redémarrage ou recréation du conteneur.

**La version de Hermes est fixe** : l'image est épinglée par son empreinte dans `docker-compose.yml`. En changer est
une décision : modifier cette ligne dans un commit, puis sur le serveur `git pull`, `docker compose pull` et
`python3 install.py`. Revenir en arrière : revenir au commit précédent, et la même suite.

## L'organisation du code

```
install.py                   point d'entrée : lit l'option, appelle son fichier
installation/
├── commun.py                affichage OK / ÉCHEC / ATTENTION, questions, lancement des commandes
├── verifications.py         Linux, Docker, Compose, ports, mémoire
├── env.py                   le .env : création, complément, reconfiguration
├── demarrage.py             up -d, attente, contrôle de la connexion au Dashboard
├── reglages.py              applique reglages.conf
├── modele.py                l'assistant hermes model
├── installer.py             l'option par défaut : toute l'installation
├── reconfigurer.py          l'option --reconfigurer
├── pare_feu.py              l'option --pare-feu
├── vault.py                 l'option --vault
└── hermes-vault.sh          la commande imposée à la clé de Hermes sur le serveur (installée par --vault)
```

**Ajouter une option** : écrire un fichier `installation/<nom>.py` qui expose `executer()`, puis ajouter sa ligne dans
la table `OPTIONS` d'`install.py`. La première ligne de sa docstring devient son aide dans `--help`.
