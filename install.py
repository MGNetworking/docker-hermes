#!/usr/bin/env python3
"""Installe Hermes sur un serveur Linux, avec Docker.

Usage, depuis le dossier du dépôt, sur le serveur :
    python3 install.py

Dans l'ordre, une ligne OK, ÉCHEC ou ATTENTION par point :
1. les vérifications : Linux, Docker, Compose v2, démon joignable, ports libres, mémoire disponible ;
2. le .env : créé depuis .env.example (ou gardé), avec l'UID et le GID de l'utilisateur, la clé de l'API générée,
   le mot de passe du Dashboard, les clés des modèles, Telegram et les plafonds de ressources ;
3. le démarrage : `docker compose config`, `docker compose up -d`, puis l'attente du healthcheck ;
4. le modèle : propose de lancer l'assistant `hermes model` dans le conteneur.

Aucun secret n'est affiché ni passé en ligne de commande ; le .env est créé lisible par son seul propriétaire.
Relancer le script est sans danger : un .env existant n'est jamais écrasé sans accord.
"""

from __future__ import annotations

import getpass
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"
CONTAINER = "hermes"
LLM_KEYS = ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]
SECRETS = {*LLM_KEYS, "API_SERVER_KEY", "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", "TELEGRAM_BOT_TOKEN"}
HEALTH_TIMEOUT = 180  # secondes


class Stop(Exception):
    """Une étape impossible : le message dit quoi faire."""


def ok(msg: str) -> None:
    print(f"OK        {msg}")


def warn(msg: str) -> None:
    print(f"ATTENTION {msg}")


def fail(msg: str) -> None:
    print(f"ÉCHEC     {msg}")


def run(command: list[str], capture: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, capture_output=capture, text=True, check=False)


# ── 1. Les vérifications ──────────────────────────────────────────────────────────────────────────────


def check_system() -> None:
    if not sys.platform.startswith("linux"):
        raise Stop("ce script s'installe sur un serveur Linux")
    ok("Linux")
    if not shutil.which("docker"):
        raise Stop("Docker est introuvable : installer Docker Engine 24 ou plus")
    if run(["docker", "info"]).returncode != 0:
        raise Stop("le démon Docker ne répond pas (est-il démarré ? l'utilisateur est-il dans le groupe docker ?)")
    ok(f"Docker {run(['docker', 'version', '--format', '{{.Server.Version}}']).stdout.strip()}")
    compose = run(["docker", "compose", "version", "--short"])
    if compose.returncode != 0:
        raise Stop("Docker Compose v2 est introuvable (la commande `docker compose`)")
    ok(f"Docker Compose {compose.stdout.strip()}")


def hermes_running() -> bool:
    out = run(["docker", "ps", "--filter", f"name=^{CONTAINER}$", "--format", "{{.Names}}"]).stdout
    return out.strip() == CONTAINER


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return False
    return True


def check_ports(values: dict[str, str]) -> None:
    if hermes_running():
        warn("Hermes tourne déjà : vérification des ports sautée (il les occupe)")
        return
    for name, default in (("HERMES_DASHBOARD_PORT", "9119"), ("API_SERVER_PORT", "8642")):
        port = int(values.get(name) or default)
        if not port_free(port):
            raise Stop(f"le port {port} ({name}) est déjà occupé : en choisir un autre dans le .env")
        ok(f"port {port} libre ({name})")


def mem_available_gib() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1024 / 1024
    return 0.0


def to_gib(limit: str) -> float:
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([GgMm])", limit.strip())
    if not m:
        return 0.0
    value = float(m.group(1))
    return value if m.group(2).lower() == "g" else value / 1024


def check_memory(values: dict[str, str]) -> None:
    available = mem_available_gib()
    limit = to_gib(values.get("HERMES_MEM_LIMIT") or "8G")
    if available < limit:
        warn(f"mémoire disponible {available:.1f} Gio, plafond de Hermes {limit:g} Gio : "
             "il pourra manquer de place en pic (le swap sert de filet)")
    else:
        ok(f"mémoire disponible {available:.1f} Gio, plafond de Hermes {limit:g} Gio")


# ── 2. Le .env ────────────────────────────────────────────────────────────────────────────────────────

KEY_LINE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)=(.*)$")


def read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = KEY_LINE.match(line)
        if m:
            values[m.group(1)] = m.group(2).strip()
    return values


def render_env(template: str, values: dict[str, str]) -> str:
    """Le modèle, avec chaque clé connue remplacée (et décommentée si elle reçoit une valeur)."""
    out = []
    for line in template.splitlines():
        m = KEY_LINE.match(line)
        if m and m.group(1) in values and values[m.group(1)] != "":
            line = f"{m.group(1)}={values[m.group(1)]}"
        out.append(line)
    return "\n".join(out) + "\n"


def write_env(content: str) -> None:
    fd = os.open(ENV, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(ENV, 0o600)


def ask(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {question}{suffix} : ").strip()
    return answer or default


def ask_yes(question: str, default: bool = True) -> bool:
    answer = input(f"  {question} [{'O/n' if default else 'o/N'}] : ").strip().lower()
    return default if not answer else answer in ("o", "oui", "y", "yes")


def ask_secret(question: str) -> str:
    return getpass.getpass(f"  {question} (rien ne s'affiche) : ").strip()


def ask_password() -> str:
    while True:
        first = ask_secret("Mot de passe du Dashboard")
        if len(first) < 12:
            print("  12 caractères au moins.")
            continue
        if first == ask_secret("Le même, pour confirmer"):
            return first
        print("  Les deux saisies diffèrent.")


def ask_llm_keys(current: dict[str, str]) -> dict[str, str]:
    print("\nClés des modèles : au moins une. Entrée seule pour passer.")
    keys: dict[str, str] = {}
    for name in LLM_KEYS:
        if current.get(name):
            if ask_yes(f"{name} est déjà renseignée : la garder ?"):
                keys[name] = current[name]
                continue
        elif os.environ.get(name):
            if ask_yes(f"{name} existe dans l'environnement de ce terminal : l'utiliser ?"):
                keys[name] = os.environ[name]
                continue
        value = ask_secret(name)
        if value:
            keys[name] = value
    if not keys:
        raise Stop("aucune clé de modèle : Hermes ne peut pas fonctionner sans")
    return keys


def ask_telegram(current: dict[str, str]) -> dict[str, str]:
    print("\nTelegram : le jeton du bot (BotFather) et ton identifiant (@userinfobot). Entrée seule pour passer.")
    token = current.get("TELEGRAM_BOT_TOKEN", "")
    if not (token and ask_yes("Le jeton du bot est déjà renseigné : le garder ?")):
        token = ask_secret("TELEGRAM_BOT_TOKEN")
    if not token:
        return {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_ALLOWED_USERS": ""}
    while True:
        users = ask("Identifiants autorisés (nombres, séparés par des virgules)",
                    current.get("TELEGRAM_ALLOWED_USERS", ""))
        if re.fullmatch(r"\d+(\s*,\s*\d+)*", users):
            return {"TELEGRAM_BOT_TOKEN": token, "TELEGRAM_ALLOWED_USERS": users.replace(" ", "")}
        print("  Obligatoire avec un jeton : sans cette liste, n'importe qui pourrait parler au bot.")


def configure_env() -> dict[str, str]:
    if not EXAMPLE.exists():
        raise Stop(".env.example est introuvable : lancer le script depuis le dossier du dépôt")
    current = read_env(ENV) if ENV.exists() else {}
    if current:
        filled = [k for k, v in current.items() if v and k in SECRETS]
        print(f"\nUn .env existe déjà (secrets renseignés : {', '.join(filled) or 'aucun'}).")
        if not ask_yes("Le reconfigurer ?", default=False):
            ok(".env gardé tel quel")
            return current

    print("\nConfiguration du .env")
    values = dict(current)
    values["PUID"], values["PGID"] = str(os.getuid()), str(os.getgid())
    if not current.get("API_SERVER_KEY"):
        values["API_SERVER_KEY"] = secrets.token_hex(32)
    values["HERMES_DASHBOARD_BASIC_AUTH_USERNAME"] = ask(
        "Utilisateur du Dashboard", current.get("HERMES_DASHBOARD_BASIC_AUTH_USERNAME") or "admin")
    if not (current.get("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD") and ask_yes("Garder le mot de passe du Dashboard ?")):
        values["HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"] = ask_password()
    values.update(ask_llm_keys(current))
    values.update(ask_telegram(current))
    cpus = os.cpu_count() or 1
    values["HERMES_CPU_LIMIT"] = ask("Plafond de processeurs pour Hermes", current.get("HERMES_CPU_LIMIT") or str(min(2, cpus)))
    values["HERMES_MEM_LIMIT"] = ask("Plafond de mémoire pour Hermes (ex. 2G)", current.get("HERMES_MEM_LIMIT") or "2G")

    write_env(render_env(EXAMPLE.read_text(encoding="utf-8"), values))
    ok(f".env écrit (PUID={values['PUID']}, PGID={values['PGID']}, clé de l'API générée, lisible par toi seul)")
    return read_env(ENV)


# ── 3. Le démarrage ───────────────────────────────────────────────────────────────────────────────────


def dashboard_code(port: str) -> int | None:
    """Le code HTTP du Dashboard (401 : il demande le mot de passe), ou None s'il ne répond pas."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}", timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return None


def start(values: dict[str, str]) -> None:
    if run(["docker", "compose", "config", "--quiet"]).returncode != 0:
        raise Stop("`docker compose config` refuse le fichier : relancer la commande pour voir l'erreur")
    ok("docker-compose.yml valide")
    print("\nDémarrage (le premier téléchargement de l'image peut prendre quelques minutes)…")
    if run(["docker", "compose", "up", "-d"], capture=False).returncode != 0:
        raise Stop("`docker compose up -d` a échoué")
    port = values.get("HERMES_DASHBOARD_PORT") or "9119"
    deadline = time.monotonic() + HEALTH_TIMEOUT
    state = ""
    while time.monotonic() < deadline:
        state = run(["docker", "inspect", "-f", "{{.State.Status}} {{.State.Health.Status}}", CONTAINER]).stdout.strip()
        code = dashboard_code(port)
        if state.startswith("running") and code is not None:
            ok("Hermes démarré")
            if code == 401:
                ok(f"le Dashboard (port {port}) répond et demande le mot de passe")
            elif code == 200:
                warn(f"le Dashboard (port {port}) répond sans demander de mot de passe")
            else:
                warn(f"le Dashboard (port {port}) répond avec le code {code}")
            if not state.endswith("healthy") or state.endswith("unhealthy"):
                warn(f"état Docker : {state} (le healthcheck interroge le Dashboard sans mot de passe : à vérifier)")
            return
        time.sleep(5)
    raise Stop(f"Hermes ne répond pas après {HEALTH_TIMEOUT} s (état : {state or 'inconnu'}) : "
               "voir `docker compose logs --tail 60 hermes`")


# ── 4. Le modèle ──────────────────────────────────────────────────────────────────────────────────────


def choose_model() -> None:
    print("\nLe modèle se choisit avec l'assistant de Hermes (fournisseur, puis modèle).")
    if ask_yes("Lancer maintenant `hermes model` dans le conteneur ?"):
        run(["docker", "compose", "exec", CONTAINER, "hermes", "model"], capture=False)
    else:
        print("  Plus tard : docker compose exec hermes hermes model")


def main() -> int:
    if not sys.stdin.isatty():
        fail("le script pose des questions : le lancer dans un terminal")
        return 1
    print("=== Installation de Hermes ===\n")
    try:
        check_system()
        values = configure_env()
        print()
        check_ports(values)
        check_memory(values)
        start(values)
        choose_model()
    except Stop as e:
        fail(str(e))
        return 1
    except KeyboardInterrupt:
        print()
        fail("interrompu")
        return 130
    print("\nÀ vérifier ensuite : `docker stats --no-stream hermes`, et un message à ton bot Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
