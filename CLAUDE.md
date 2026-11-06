# CLAUDE.md — hermes

Déploiement Docker de **Hermes Agent** (NousResearch) : un agent IA exposant un Dashboard web
et une Gateway API compatible OpenAI.

Ce dépôt vit dans `D:\Projet\agentic-os\hermes` — **hors** de `D:\Projet\Docker-projet`. Il n'hérite
donc d'aucun `CLAUDE.md` intermédiaire : ce fichier est autonome.

---

## Ce que contient le dépôt

```
hermes/
├── docker-compose.yml    # configuration de production, entièrement paramétrée par .env
├── .env.example          # template versionné
├── .env                  # secrets réels — gitignoré
├── README.md             # démarrage rapide
└── audi-technique.md     # audit technique en 21 points — la référence détaillée
```

Le dépôt ne contient **pas** de code applicatif : l'image `nousresearch/hermes-agent` vient
de l'amont. Ce projet est de l'exploitation, pas du développement.

`data/` est gitignoré et n'existe qu'à l'exécution.

| | |
| --- | --- |
| Dépôt | `MGNetworking/docker-hermes`, branche `master` |
| Image | `nousresearch/hermes-agent:latest` |
| Conteneur | `hermes` |
| Documentation amont | https://hermes-agent.nousresearch.com/docs/ |

---

## Surfaces exposées

| Port | Service | Variable |
| ---- | ------- | -------- |
| 8642 | Gateway API (compatible OpenAI, auth Bearer) | `API_SERVER_PORT` |
| 9119 | Dashboard web | `HERMES_DASHBOARD_PORT` |

Les deux bindent `0.0.0.0` par défaut. Sur une machine accessible depuis le réseau, cela
signifie exposé — l'authentification n'est pas optionnelle (voir plus bas).

---

## Sécurité — les trois points qui comptent

**1. `/var/run/docker.sock` est monté dans le conteneur.**
C'est le Docker Backend : Hermes pilote le démon Docker de l'hôte. Un accès au socket Docker
équivaut à un accès root sur l'hôte. Conséquence directe : quiconque atteint la Gateway API ou
le Dashboard peut, via l'agent, agir en root sur la machine.

Ce montage est un choix assumé, pas un oubli. Ne pas le retirer sans demande — mais ne jamais
proposer d'exposer Hermes publiquement sans authentification ni reverse proxy devant.

**2. `API_SERVER_KEY` n'a pas de valeur par défaut.**
Contrairement à toutes les autres variables du compose, elle s'écrit `${API_SERVER_KEY}` sans
fallback : le `up` échoue si elle est absente. C'est volontaire. La générer avec
`openssl rand -hex 32`.

**3. Authentification du Dashboard obligatoire hors loopback.**
Trois méthodes mutuellement exclusives sont prévues dans le compose — Basic Auth locale
(option A, active), OAuth Nous Portal (B), OIDC (C). Une seule à la fois.

**Aucune clé API ne va dans `docker-compose.yml`.** Toutes passent par `.env`, qui est
gitignoré. `.env.example` documente les clés avec des valeurs vides — c'est ce couple qui est
versionné, et le modèle à préserver.

---

## Persistance

Un seul point de montage porte tout l'état : `./data` → `/opt/data`.

```
/opt/data/
├── .env          # config interne du gateway
├── config.yaml
├── sessions/     # historique des conversations
├── memories/     # mémoire persistante de l'agent
├── skills/       # extensions installées
├── logs/         # rotation 10 × 1 Mo
└── home/         # HOME des sous-processus par profil
```

**Migrer Hermes ailleurs = copier `data/`, `docker-compose.yml` et `.env`.** Rien d'autre.

`data/` contient l'historique et la mémoire de l'agent, et n'est sauvegardé nulle part
automatiquement. Ne jamais proposer `docker compose down -v` ni la suppression de `./data`.

---

## Particularités du compose

- **`shm_size: 1g`** — requis par Chromium/Playwright pour l'automatisation de navigateur.
  Sans cela, les sessions navigateur plantent sans message clair. Ne pas réduire.
- **`PUID` / `PGID`** — utilisés par s6-overlay pour ajuster les droits de `/opt/data`.
  Doivent correspondre au propriétaire du dossier sur l'hôte (`id -u && id -g`).
  À distinguer de `HERMES_UID`/`HERMES_GID` (10000 par défaut), qui sont l'identité *interne*
  du process.
- **Healthcheck par `curl` sur le Dashboard** — l'image n'expose aucun endpoint `/health`.
  Si le Dashboard est désactivé (`HERMES_DASHBOARD=0`), le healthcheck devient faux négatif
  et il faut le rebasculer sur la Gateway.
- **`deploy.resources`** — 4 CPU / 8 Go par défaut, réservation 1 CPU / 2 Go. Honoré par
  Compose v2 hors Swarm.
- **Fuseau** via `/etc/localtime:ro`, pas via une variable `TZ`.
- **Style des variables** : `${VAR:-défaut}` en notation map. Ce dépôt ne suit pas la
  convention de `Docker-projet` où la variable porte le mapping de port complet — c'est
  cohérent en interne, ne pas l'aligner.
- **`HERMES_ALLOW_ROOT_GATEWAY`** et **`HERMES_SKIP_CONFIG_MIGRATION`** sont des leviers de
  diagnostic, commentés. Ne pas les activer pour contourner une erreur : ce sont des
  symptômes à traiter à la source.

---

## Exploitation

```bash
docker compose up -d
docker compose logs -f
docker compose config          # valider après toute modification du compose
```

Prérequis : Docker Engine 24+, Compose v2, 2 Go de RAM disponibles au minimum.

---

## Où chercher

`audi-technique.md` est l'audit technique complet et couvre en détail les providers LLM,
les volumes, l'intégration reverse proxy (Caddy / Traefik / Nginx), les ressources et la
sécurité. **Le consulter avant de répondre sur ces sujets** — il est plus précis que le
README, et le nom du fichier porte une coquille (`audi-` pour `audit-`) qui le rend facile
à manquer.
