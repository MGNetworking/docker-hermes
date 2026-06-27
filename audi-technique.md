# Hermes Docker — Audit technique pour une installation industrialisée

## Sommaire

- [Objectif](#objectif)
- [1. Image Docker](#1-image-docker)
- [2. Docker Compose officiel](#2-docker-compose-officiel)
- [3. Volumes](#3-volumes)
- [4. Configuration](#4-configuration)
- [5. Variables d'environnement](#5-variables-denvironnement)
- [6. UID / GID](#6-uid--gid)
- [7. Docker Backend](#7-docker-backend)
- [8. docker.sock](#8-dockersock)
- [9. Dashboard](#9-dashboard)
- [10. Gateway API](#10-gateway-api)
- [11. Nous Portal](#11-nous-portal)
- [12. Providers LLM](#12-providers-llm)
- [13. Réseau Docker](#13-réseau-docker)
- [14. Ports](#14-ports)
- [15. Reverse Proxy](#15-reverse-proxy)
- [16. Healthcheck](#16-healthcheck)
- [17. Logs](#17-logs)
- [18. Sauvegarde et migration](#18-sauvegarde-et-migration)
- [19. Ressources Docker](#19-ressources-docker)
- [20. Sécurité](#20-sécurité)
- [21. Docker Compose final](#21-docker-compose-final)
- [Sources](#sources)

---

## Objectif

Construire une installation Docker d'Hermes :

* entièrement configurable via `docker-compose.yml`
* sans script de démarrage spécifique
* avec persistance complète
* facilement sauvegardable
* facilement migrable
* sécurisée
* extensible (Reverse Proxy, Ollama, MCP, PostgreSQL, etc.)

---

# 1. Image Docker

## Résultat

| Paramètre | Valeur |
|-----------|--------|
| Image officielle | `nousresearch/hermes-agent:latest` |
| Registry | Docker Hub |
| Tags | `latest` + versioning sémantique (ex. `0.9.1`) |
| Politique recommandée | `latest` en dev, tag fixe en production |

**Erreur dans le docker-compose initial :** l'image était `nousresearch/hermes:latest` — le nom correct est `nousresearch/hermes-agent:latest`.

## Base de l'image

Construite sur `debian:13.4` avec :
- Python 3.13
- Node.js 22 + npm
- Playwright + Chromium
- docker-cli (pour le Docker Backend)
- openssh-client
- s6-overlay v3 (superviseur PID 1)

---

# 2. Docker Compose officiel

## Analyse du compose officiel

| Élément | Valeur officielle |
|---------|-----------------|
| Image | `nousresearch/hermes-agent:latest` |
| Command | `gateway run` |
| Network mode | `host` (dans le compose officiel) |
| Volume | `~/.hermes:/opt/data` |
| Restart | `unless-stopped` |

**Note :** le compose officiel utilise `network_mode: host`. Notre version utilise un réseau bridge nommé avec publication de ports, ce qui est plus sécurisé et extensible.

---

# 3. Volumes

## Structure complète de `/opt/data`

| Dossier / Fichier | Contenu | Persistant |
|-------------------|---------|-----------|
| `.env` | Clés API et secrets | **Oui** |
| `config.yaml` | Configuration du gateway | **Oui** |
| `sessions/` | Historique des conversations | **Oui** |
| `memories/` | Mémoire persistante | **Oui** |
| `skills/` | Extensions installées | **Oui** |
| `logs/` | Journaux tournants (10 × 1 Mo) | Optionnel |
| `home/` | HOME des sous-processus par profil | **Oui** |

## Stratégie de montage

```yaml
volumes:
  - ./data:/opt/data           # toute la persistance
  - /var/run/docker.sock:/var/run/docker.sock   # Docker Backend
  - /etc/localtime:/etc/localtime:ro            # Fuseau horaire
```

**Un seul volume suffit** pour reconstruire entièrement Hermes sur un nouveau serveur.

---

# 4. Configuration

## Emplacement

`/opt/data/config.yaml` (monté via le volume `./data`)

## Paramètres clés

```yaml
# Exemple de config.yaml
tool_loop_guardrails:
  hard_stop_enabled: true
  hard_stop_after:
    exact_failure: 5
    idempotent_no_progress: 5
```

Pour connecter Ollama depuis le réseau Docker :
```yaml
# Dans config.yaml
providers:
  ollama:
    base_url: http://ollama:11434
```

---

# 5. Variables d'environnement

## Tableau complet

| Variable | Obligatoire | Défaut | Description |
|----------|-------------|--------|-------------|
| `PUID` | Non | `1000` | UID hôte pour chown du volume |
| `PGID` | Non | `1000` | GID hôte pour chown du volume |
| `HERMES_UID` | Non | `10000` | UID interne du process |
| `HERMES_GID` | Non | `10000` | GID interne du process |
| `HERMES_DASHBOARD` | Non | `0` | Activer le Dashboard (`1`) |
| `HERMES_DASHBOARD_HOST` | Non | `0.0.0.0` | Adresse d'écoute dashboard |
| `HERMES_DASHBOARD_PORT` | Non | `9119` | Port dashboard |
| `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` | Oui* | — | Utilisateur dashboard |
| `HERMES_DASHBOARD_BASIC_AUTH_PASSWORD` | Oui* | — | Mot de passe dashboard |
| `HERMES_DASHBOARD_OAUTH_CLIENT_ID` | Oui* | — | OAuth Nous Portal |
| `HERMES_DASHBOARD_OIDC_ISSUER` | Oui* | — | Issuer OIDC |
| `HERMES_DASHBOARD_OIDC_CLIENT_ID` | Oui* | — | Client ID OIDC |
| `API_SERVER_ENABLED` | Non | `false` | Activer l'API Gateway |
| `API_SERVER_HOST` | Non | `0.0.0.0` | Adresse d'écoute API |
| `API_SERVER_PORT` | Non | `8642` | Port API |
| `API_SERVER_KEY` | **Oui** | — | Token d'authentification API |
| `API_SERVER_CORS_ORIGINS` | Non | — | Origines CORS autorisées |
| `ANTHROPIC_API_KEY` | Non** | — | Clé Anthropic |
| `OPENAI_API_KEY` | Non** | — | Clé OpenAI |
| `GOOGLE_API_KEY` | Non** | — | Clé Google |
| `TELEGRAM_BOT_TOKEN` | Non | — | Token bot Telegram |
| `DISCORD_BOT_TOKEN` | Non | — | Token bot Discord |
| `HERMES_SKIP_CONFIG_MIGRATION` | Non | `0` | Passer la migration config (diagnostic) |
| `HERMES_ALLOW_ROOT_GATEWAY` | Non | `0` | Autoriser root (déconseillé) |

\* Une méthode d'auth est obligatoire si le dashboard est exposé sur une interface non-loopback (depuis juin 2026).
\** Au moins une clé provider est nécessaire pour utiliser les LLM.

---

# 6. UID / GID

## Mécanisme

L'image utilise **s6-overlay v3** comme PID 1. Au démarrage :
1. s6 lit `PUID`/`PGID`
2. Il exécute `chown -R $PUID:$PGID /opt/data`
3. Le gateway tourne ensuite en tant que `hermes` (UID `HERMES_UID`, défaut 10000)

## Sans script de démarrage

Aucun `export UID=$(id -u)` nécessaire. Il suffit de définir dans `.env` :
```
PUID=1000
PGID=1000
```

Obtenir les valeurs de l'hôte : `id -u && id -g`

---

# 7. Docker Backend

## Fonctionnement

Hermes peut piloter le démon Docker de l'hôte pour :
- `docker build` / `docker run`
- Inspection de conteneurs
- Gestion d'images

L'image inclut **docker-cli**. Le socket est transmis via :
```yaml
volumes:
  - /var/run/docker.sock:/var/run/docker.sock
```

---

# 8. docker.sock

## Risques et bonnes pratiques

| Aspect | Détail |
|--------|--------|
| Risque principal | Accès root indirect à l'hôte |
| Processus dans le conteneur | Non-root (UID 10000) par défaut |
| Alternative plus sécurisée | Docker socket proxy (Tecnativa) |
| Ne jamais faire | `HERMES_ALLOW_ROOT_GATEWAY=1` en production |

## Option sécurisée : Socket Proxy

```yaml
services:
  dockerproxy:
    image: tecnativa/docker-socket-proxy
    environment:
      CONTAINERS: 1
      IMAGES: 1
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    networks:
      - hermes

  hermes:
    environment:
      DOCKER_HOST: tcp://dockerproxy:2375
    networks:
      - hermes
```

---

# 9. Dashboard

## Architecture

- Intégré au même conteneur que le gateway
- Supervisé par s6-overlay (redémarrage automatique)
- Activé via `HERMES_DASHBOARD=1`

## Authentification (obligatoire depuis juin 2026)

Trois options mutuellement exclusives :
1. Basic Auth : `HERMES_DASHBOARD_BASIC_AUTH_USERNAME` + `_PASSWORD`
2. OAuth Nous Portal : `HERMES_DASHBOARD_OAUTH_CLIENT_ID`
3. OIDC : `HERMES_DASHBOARD_OIDC_ISSUER` + `HERMES_DASHBOARD_OIDC_CLIENT_ID`

---

# 10. Gateway API

## Caractéristiques

| Aspect | Détail |
|--------|--------|
| Protocole | HTTP REST compatible OpenAI |
| Port par défaut | `8642` |
| Authentification | Bearer token (`API_SERVER_KEY`) |
| Clients compatibles | Open WebUI, Angular, Mobile, Discord, Telegram |

## Sécurisation

```bash
# Générer une clé forte
openssl rand -hex 32
```

---

# 11. Nous Portal

## Rôle

Service d'authentification unifié NousResearch qui donne accès à :
- Plusieurs modèles LLM
- Outils Gateway (recherche web, génération d'images, TTS, browser)

## Caractéristiques

| Aspect | Détail |
|--------|--------|
| Obligatoire | Non — tous les providers fonctionnent sans |
| Avantage | Une seule clé pour modèles + outils |
| Configuration | `hermes setup --portal` |
| Usage Dashboard | Option OAuth (`HERMES_DASHBOARD_OAUTH_CLIENT_ID`) |

---

# 12. Providers LLM

| Provider | Variable | Notes |
|----------|----------|-------|
| Anthropic | `ANTHROPIC_API_KEY` | Claude 3.x, 4.x |
| OpenAI | `OPENAI_API_KEY` | GPT-4o, o1 |
| Google | `GOOGLE_API_KEY` | Gemini |
| OpenRouter | `OPENROUTER_API_KEY` | Multi-providers |
| Nous Portal | Via setup | Modèles Nous + outils |
| Ollama | `OLLAMA_BASE_URL` | Inférence locale |

---

# 13. Réseau Docker

## Architecture recommandée

```yaml
networks:
  hermes:
    driver: bridge

services:
  hermes:
    networks: [hermes]
  ollama:
    networks: [hermes]
```

Communication interne par nom de conteneur : `http://ollama:11434`

---

# 14. Ports

| Port | Service | Obligatoire | Exposition |
|------|---------|-------------|-----------|
| `8642` | Gateway API | Pour clients externes | Publique ou Reverse Proxy |
| `9119` | Dashboard | Si `HERMES_DASHBOARD=1` | Interne ou Reverse Proxy |

**Recommandation :** n'exposer les ports que derrière un Reverse Proxy avec HTTPS.

---

# 15. Reverse Proxy

## Caddy (recommandé)

```yaml
services:
  caddy:
    image: caddy:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile
      - caddy_data:/data
    networks:
      - hermes
```

```
# Caddyfile
hermes.example.com {
  reverse_proxy hermes:9119
}
api.hermes.example.com {
  reverse_proxy hermes:8642
}
```

---

# 16. Healthcheck

## Implémentation

Aucun endpoint `/health` natif. On sonde le Dashboard ou l'API :

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "-s", "http://localhost:9119"]
  interval: 30s
  timeout: 10s
  retries: 5
  start_period: 30s
```

La résilience principale repose sur `restart: unless-stopped` + s6-overlay (redémarrage interne en ~1 s).

---

# 17. Logs

## Emplacement

| Type | Chemin |
|------|--------|
| Docker | `docker logs -f hermes` |
| Fichiers | `/opt/data/logs/gateways/<profil>/current` |
| Rotation | 10 archives × 1 Mo (automatique via s6) |

---

# 18. Sauvegarde et migration

## Procédure complète

```bash
# Arrêt propre
docker compose down

# Sauvegarde du volume (toute la persistance)
tar -czf hermes-backup-$(date +%Y%m%d).tar.gz ./data/

# Migration : copier le tar + docker-compose.yml + .env sur le nouveau serveur
# Extraire et relancer
tar -xzf hermes-backup-*.tar.gz
docker compose up -d
```

**Important :** ne jamais lancer deux conteneurs Hermes sur le même `/opt/data` simultanément.

---

# 19. Ressources Docker

| Ressource | Minimum | Recommandé | Config actuelle |
|-----------|---------|-----------|----------------|
| CPU | 1 core | 2 cores | 4 (limite) |
| RAM | 1 GB | 2–4 GB | 8 GB (limite) |
| Disque `/opt/data` | 500 MB | 2+ GB | — |
| Mémoire partagée | — | 1 GB (Playwright) | `shm_size: 1g` |

---

# 20. Sécurité

## Checklist

| Point | Statut | Action |
|-------|--------|--------|
| Image non-root | ✅ | UID 10000 par défaut |
| Auth Dashboard | ⚠️ | Obligatoire — configurer `HERMES_DASHBOARD_BASIC_AUTH_*` |
| Auth API | ✅ | `API_SERVER_KEY` à générer |
| docker.sock | ⚠️ | Envisager un socket proxy en production |
| Secrets en `.env` | ✅ | Ne jamais committer `.env` |
| CORS | ⚠️ | Restreindre `API_SERVER_CORS_ORIGINS` si exposition publique |
| Ports | ⚠️ | Passer derrière Reverse Proxy + HTTPS |
| Volumes | ✅ | Répertoire local `./data`, propriétaire contrôlé via PUID/PGID |

---

# 21. Docker Compose final

Voir [docker-compose.yml](docker-compose.yml) — fichier de production généré à l'issue de cet audit.

## Corrections apportées par rapport au compose initial

| Problème initial | Correction |
|-----------------|-----------|
| `image: nousresearch/hermes:latest` | → `nousresearch/hermes-agent:latest` |
| Pas de `command` | → `command: gateway run` |
| `HERMES_UID`/`HERMES_GID` seuls | → ajout de `PUID`/`PGID` pour les permissions volume |
| Dashboard non activé | → `HERMES_DASHBOARD: 1` |
| Pas d'auth dashboard | → `HERMES_DASHBOARD_BASIC_AUTH_*` |
| Pas de clé API | → `API_SERVER_KEY` |
| Ressources surdimensionnées sans réservation | → ajout `reservations` |
| Pas de `shm_size` | → `shm_size: 1g` pour Playwright |
| `start_period` absent du healthcheck | → ajout `start_period: 30s` |
| Ports en dur | → paramétrisés via variables `.env` |

---

# Sources

| Ressource | URL |
|-----------|-----|
| Documentation officielle | https://hermes-agent.nousresearch.com/docs/ |
| Guide Docker | https://hermes-agent.nousresearch.com/docs/user-guide/docker |
| GitHub | https://github.com/NousResearch/hermes-agent |
| Docker Hub | https://hub.docker.com/r/nousresearch/hermes-agent |
