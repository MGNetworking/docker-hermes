# Le `docker-compose.yml`, réglage par réglage

Le compose démarre deux services : **`hermes`**, l'agent, et **`docker-proxy`**, le filtre qui lui donne un accès à
Docker en lecture seule. Tous les réglages variables passent par le `.env` (préparé par `install.py`, voir
[installation.md](installation.md)) ; aucun secret n'est écrit dans le compose.

## Le service `hermes`

| Réglage | Ce qu'il fait | Pourquoi |
|---|---|---|
| `image: nousresearch/hermes-agent@sha256:…` | L'image officielle de Hermes, **épinglée par son empreinte** (v0.23.0) | `latest` change à chaque publication ; une version fixe ne change que par un commit, et se défait de même |
| `container_name: hermes` | Le nom du conteneur | Pour les commandes `docker compose exec hermes …` et les vérifications d'`install.py` |
| `command: gateway run` | Lance la passerelle (messageries, tâches planifiées, API), et le Dashboard si `HERMES_DASHBOARD=1` | Le mode « service permanent » de Hermes |
| `restart: unless-stopped` | Docker relance Hermes au démarrage du serveur et après un plantage | Il redémarre seul avec la machine ; un arrêt fait à la main (`docker compose stop`) est respecté |
| `hostname: hermes` | Le nom de la machine vu de l'intérieur du conteneur | Lisibilité des journaux et des invites |

### L'environnement

| Variables | Ce qu'elles font | Pourquoi |
|---|---|---|
| `PUID`, `PGID` | L'UID et le GID du propriétaire de `data/` sur le serveur | Le conteneur rend `data/` à ce propriétaire au démarrage : sans eux, les fichiers de Hermes appartiendraient à un autre utilisateur |
| `HERMES_DASHBOARD`, `HERMES_DASHBOARD_HOST`, `HERMES_DASHBOARD_PORT` | Activent le Dashboard web et fixent son adresse d'écoute et son port | L'interface web pour converser avec Hermes et voir sa mémoire, ses sessions, ses tâches |
| `HERMES_DASHBOARD_BASIC_AUTH_USERNAME`, `…_PASSWORD` | L'utilisateur et le mot de passe du Dashboard | Depuis juin 2026, Hermes refuse d'ouvrir un Dashboard accessible depuis le réseau sans authentification. La connexion passe par une page `/login` |
| `HERMES_DASHBOARD_BASIC_AUTH_SECRET` | La clé qui signe les sessions du Dashboard (générée par `install.py`) | Sans elle, une clé tirée au hasard à chaque démarrage déconnecterait à chaque redémarrage |
| `API_SERVER_ENABLED`, `API_SERVER_HOST`, `API_SERVER_PORT` | Activent la Gateway API, compatible OpenAI | Pour qu'un autre programme parle à Hermes par HTTP |
| `API_SERVER_KEY` | La clé exigée par la Gateway API (générée par `install.py`) | **Aucune valeur par défaut, volontairement** : `docker compose up` échoue si elle manque |
| `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `OPENROUTER_API_KEY` | Les clés des fournisseurs de modèles ; au moins une | Hermes appelle son modèle chez un fournisseur. DeepSeek a un fournisseur intégré (`deepseek`) qui lit `DEEPSEEK_API_KEY` |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` | Le jeton du bot Telegram et les identifiants autorisés à lui parler | **Sans la liste, n'importe qui trouvant le bot pourrait lui donner des ordres** |
| `DOCKER_HOST: tcp://docker-proxy:2375` | Hermes parle à Docker par le service `docker-proxy` | Il ne voit jamais le vrai socket Docker (voir plus bas) |
| `HERMES_SKIP_CONFIG_MIGRATION`, `HERMES_ALLOW_ROOT_GATEWAY` (en commentaire) | Des leviers de diagnostic | Jamais pour contourner une erreur : ce sont des symptômes à traiter à la source |

### Les volumes

| Volume | Ce qu'il fait | Pourquoi |
|---|---|---|
| `./data:/opt/data` | **Tout l'état de Hermes** sur le serveur : sa configuration (`config.yaml`), ses sessions, sa mémoire, ses skills, ses journaux | Ces données survivent à la recréation du conteneur et aux mises à jour ; migrer Hermes = copier `data/`, le compose et le `.env`. `data/` n'est sauvegardé nulle part automatiquement |
| `/etc/localtime` (lecture seule) | Le fuseau horaire du serveur | Des heures justes dans les journaux et les tâches planifiées |
| *pas de* `/var/run/docker.sock` | — | Le socket complet donnerait à Hermes un accès root au serveur |

### Le réseau, la mémoire, la santé, les ressources

| Réglage | Ce qu'il fait | Pourquoi |
|---|---|---|
| `ports` | Publient le Dashboard et la Gateway API sur le serveur (`HERMES_DASHBOARD_PORT`, `API_SERVER_PORT`) | Pour y accéder depuis le réseau ; le pare-feu du serveur décide d'où ([pare-feu-serveur.md](pare-feu-serveur.md)) |
| `networks: hermes` | Un réseau Docker propre à Hermes et à son proxy | `docker-proxy` n'est joignable que par Hermes, jamais depuis le réseau |
| `depends_on: docker-proxy` | Démarre le proxy avant Hermes | Hermes trouve Docker dès son démarrage |
| `shm_size: 1g` | La mémoire partagée du conteneur | Requise par le navigateur que Hermes pilote (Chromium) ; sans elle, les sessions navigateur plantent sans message clair |
| `healthcheck` | Docker interroge le Dashboard toutes les 30 s | Hermes n'a pas d'adresse `/health` : le Dashboard sert de témoin |
| `deploy.resources.limits` (`HERMES_CPU_LIMIT`, `HERMES_MEM_LIMIT`) | Le plafond de processeurs et de mémoire | Hermes ne peut pas affamer les autres services du serveur ; au-delà, seul son conteneur est arrêté puis relancé |
| `deploy.resources.reservations` | 1 cœur et 2 Go réservés | Hermes garde de quoi tourner même quand la machine est chargée |

## Le service `docker-proxy`

| Réglage | Ce qu'il fait | Pourquoi |
|---|---|---|
| `image: tecnativa/docker-socket-proxy:v0.5.0` | Un filtre de l'API Docker, version épinglée | Seul conteneur à monter le socket Docker |
| `CONTAINERS: 1`, `IMAGES: 1` | Autorisent la lecture des conteneurs et des images | Hermes peut voir l'état des conteneurs et te le rapporter |
| `POST: 0` | Refuse toute écriture | Créer un conteneur, `exec`, volumes, réseaux, build, et même démarrer ou arrêter : refusés. Vérifié le 2026-11-07 : avec `POST=1`, la création de conteneurs (donc un accès root) redeviendrait possible |
| `volumes: /var/run/docker.sock` | Le socket Docker du serveur | C'est lui que le proxy filtre |
| *aucun* `ports` | — | Le proxy n'est joignable que par Hermes, sur le réseau `hermes` |
| `restart: unless-stopped` | Redémarre avec le serveur | Comme Hermes |

Démarrer ou arrêter un conteneur reste donc à l'utilisateur, depuis sa propre session.
