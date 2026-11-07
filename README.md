# Hermes — Déploiement Docker

Déploiement conteneurisé de [Hermes Agent](https://hermes-agent.nousresearch.com) (NousResearch) — portable, persistant et prêt pour la production.

---

## Qu'est-ce que Hermes ?

Hermes est un agent IA développé par NousResearch. Il s'appuie sur les grands modèles de langage (Anthropic, OpenAI, Google, Ollama…) et expose ses capacités via :

- un **Dashboard Web** pour interagir directement avec l'agent
- une **Gateway API** compatible OpenAI pour l'intégrer à n'importe quel client (Open WebUI, applications mobiles, Discord, Telegram…)
- plus de **20 plateformes de messagerie** supportées nativement

---

## Ce que fait ce dépôt

Ce projet fournit une configuration Docker prête à l'emploi pour déployer Hermes sur n'importe quel serveur Linux, sans installation manuelle ni script de démarrage.

```
hermes/
├── install.py            # Installation guidée : vérifications, .env, démarrage, réglages (point d'entrée)
├── installation/         # Une étape ou une option par fichier, appelées par install.py
├── reglages.conf         # Les réglages de Hermes, appliqués par install.py
├── docker-compose.yml    # Configuration Docker de production
├── docs/                 # Installation, compose, pare-feu (voir « Documentation »)
├── .env.example          # Template des variables à configurer
├── .gitignore
├── .gitattributes
└── audi-technique.md     # Audit technique complet (21 points)
```

---

## Démarrage rapide

### 1. Installer avec le script

Sur le serveur Linux, depuis le dossier du dépôt :

```bash
python3 install.py
```

Il vérifie la machine, prépare le `.env` (sans jamais réécrire un `.env` existant), démarre Hermes, applique les
verrous de `reglages.conf` et, à la première installation, propose le choix du modèle. **Le détail, les options
(`--reconfigurer`, `--pare-feu`), les verrous et la mise à jour : [docs/installation.md](docs/installation.md).**

### 2. Sans le script

```bash
cp .env.example .env      # puis renseigner les valeurs à la main
docker compose up -d
```

### 3. Accéder aux interfaces

| Interface | URL |
|-----------|-----|
| Dashboard | http://localhost:9119 |
| Gateway API | http://localhost:8642 |
| Terminal (par SSH) | voir ci-dessous |

### 4. Parler à Hermes depuis un terminal, par SSH

Comme avec Claude Code : une conversation dans le terminal, où le copier-coller fonctionne. Depuis le PC :

```bash
ssh -t <utilisateur>@<serveur> "cd <dossier du dépôt> && docker compose exec -it hermes hermes"
```

Ou, une fois connecté au serveur, depuis le dossier du dépôt :

```bash
docker compose exec -it hermes hermes
```

C'est une session de plus, comme celle du Dashboard ou de Telegram : chacune a son propre fil de conversation.

### 5. Suivre les logs

```bash
docker compose logs -f
```

---

## Prérequis

- Docker Engine 24+
- Docker Compose v2
- Au moins **2 Go de RAM** disponibles pour le conteneur

---

## Persistance des données

Toutes les données d'Hermes sont stockées dans le dossier local `./data/`, monté sur `/opt/data` dans le conteneur. Ce dossier contient conversations, mémoire, skills, configuration et logs.

> Pour migrer Hermes sur un autre serveur, il suffit de copier `./data/`, `docker-compose.yml` et `.env`.

L'audit technique détaille la [structure complète du volume](audi-technique.md#3-volumes).

---

## Configuration avancée

Le fichier `docker-compose.yml` est entièrement paramétrable via `.env`. Les principaux axes de configuration sont documentés dans l'[audit technique](audi-technique.md) :

- [Providers LLM supportés](audi-technique.md#12-providers-llm) — Anthropic, OpenAI, Google, Ollama, OpenRouter…
- [Sécurité](audi-technique.md#20-sécurité) — auth Dashboard, clé API, docker.sock, CORS
- [Le docker-compose.yml, réglage par réglage](docs/docker-compose.md) — à quoi sert chaque réglage, et pourquoi
- [Pare-feu du serveur](docs/pare-feu-serveur.md) — UFW et les ports Docker (`DOCKER-USER`)
- [Reverse Proxy](audi-technique.md#15-reverse-proxy) — intégration Caddy / Traefik / Nginx
- [Ressources Docker](audi-technique.md#19-ressources-docker) — CPU, RAM, mémoire partagée Playwright

---

## Sécurité

- Le conteneur tourne en **utilisateur non-root** (UID 10000)
- Le Dashboard requiert une **authentification** dès qu'il est exposé hors loopback
- La Gateway API est protégée par un **token Bearer**
- Les clés API ne sont jamais stockées dans `docker-compose.yml` — uniquement dans `.env` (exclu du git)

---

## Documentation

| Ressource | Lien |
|-----------|------|
| L'installation : `install.py`, ses options, les verrous, la mise à jour | [docs/installation.md](docs/installation.md) |
| Le `docker-compose.yml`, réglage par réglage | [docs/docker-compose.md](docs/docker-compose.md) |
| Le pare-feu du serveur (`--pare-feu`) | [docs/pare-feu-serveur.md](docs/pare-feu-serveur.md) |
| Audit technique complet | [audi-technique.md](audi-technique.md) |
| Documentation officielle | https://hermes-agent.nousresearch.com/docs/ |
| GitHub NousResearch | https://github.com/NousResearch/hermes-agent |
