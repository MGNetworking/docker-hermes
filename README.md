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
├── docker-compose.yml    # Configuration Docker de production
├── .env.example          # Template des variables à configurer
├── .gitignore
├── .gitattributes
└── audi-technique.md     # Audit technique complet (21 points)
```

---

## Démarrage rapide

### 1. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Ouvrir `.env` et renseigner au minimum :

| Variable | Description |
|----------|-------------|
| `API_SERVER_KEY` | Clé d'auth de la Gateway — générer avec `openssl rand -hex 32` |
| `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` | Mot de passe du Dashboard |
| `ANTHROPIC_API_KEY` ou autre | Au moins un provider LLM |
| `PUID` / `PGID` | UID/GID de l'hôte — obtenir avec `id -u && id -g` |

### 2. Lancer le conteneur

```bash
docker compose up -d
```

### 3. Accéder aux interfaces

| Interface | URL |
|-----------|-----|
| Dashboard | http://localhost:9119 |
| Gateway API | http://localhost:8642 |

### 4. Suivre les logs

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
| Audit technique complet | [audi-technique.md](audi-technique.md) |
| Documentation officielle | https://hermes-agent.nousresearch.com/docs/ |
| GitHub NousResearch | https://github.com/NousResearch/hermes-agent |
