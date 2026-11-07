#!/usr/bin/env python3
"""Installe Hermes sur un serveur Linux, avec Docker.

Usage, depuis le dossier du dépôt, sur le serveur :
    python3 install.py                  première installation, ou mise à jour après un `git pull`
    python3 install.py --reconfigurer   reposer toutes les questions du .env

Dans l'ordre, une ligne OK, ÉCHEC ou ATTENTION par point :
1. les vérifications : Linux, Docker, Compose v2, démon joignable, ports libres, mémoire disponible ;
2. le .env :
   - absent : créé depuis .env.example, en posant les questions (UID et GID de l'utilisateur, clé de l'API
     générée, mot de passe du Dashboard, clés des modèles, Telegram, plafonds de ressources) ;
   - présent : jamais réécrit. Seules les variables apparues dans .env.example sont ajoutées à la fin (une question
     pour chaque secret, la valeur d'exemple pour le reste), après une copie de sauvegarde .env.bak ;
3. le démarrage : `docker compose config`, `docker compose up -d`, puis l'attente du Dashboard ;
4. les réglages : chaque ligne de reglages.conf appliquée avec `hermes config set`, puis un redémarrage ;
5. le modèle, à la première installation seulement : propose l'assistant `hermes model`.

Aucun secret n'est affiché ni passé en ligne de commande ; le .env est créé lisible par son seul propriétaire.
"""

from __future__ import annotations

import argparse
import getpass
import json
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
REGLAGES = ROOT / "reglages.conf"
CONTAINER = "hermes"
LLM_KEYS = ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]
GENERATED = {"API_SERVER_KEY", "HERMES_DASHBOARD_BASIC_AUTH_SECRET"}  # clés tirées au hasard, jamais demandées
SECRETS = {*LLM_KEYS, *GENERATED, "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", "TELEGRAM_BOT_TOKEN"}
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


def keys_in(text: str) -> list[str]:
    """Les clés d'un fichier .env, actives ou en commentaire, dans l'ordre."""
    keys = []
    for line in text.splitlines():
        m = KEY_LINE.match(line)
        if m and m.group(1) not in keys:
            keys.append(m.group(1))
    return keys


def complete_env() -> dict[str, str]:
    """Le .env existant n'est jamais réécrit : seules les variables nouvelles de .env.example sont ajoutées."""
    present = set(keys_in(ENV.read_text(encoding="utf-8")))
    example_text = EXAMPLE.read_text(encoding="utf-8")
    example = read_env(EXAMPLE)
    missing = [k for k in keys_in(example_text) if k not in present and k in example]
    if not missing:
        ok(".env gardé tel quel (aucune variable nouvelle dans .env.example)")
        return read_env(ENV)
    print(f"\nVariables nouvelles dans .env.example : {', '.join(missing)}")
    lines = [f"\n# --- Ajouté par install.py le {time.strftime('%Y-%m-%d')} ---"]
    for key in missing:
        if key in GENERATED:
            value = secrets.token_hex(32)
        else:
            value = ask_secret(f"{key} (Entrée pour laisser vide)") if key in SECRETS else example[key]
        lines.append(f"{key}={value}")
    backup = ENV.with_name(".env.bak")
    shutil.copy2(ENV, backup)
    os.chmod(backup, 0o600)
    with open(ENV, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    ok(f".env complété ({', '.join(missing)}), rien d'autre n'a changé ; sauvegarde : .env.bak")
    return read_env(ENV)


def configure_env(reconfigure: bool) -> tuple[dict[str, str], bool]:
    """Le .env, et s'il vient d'être créé."""
    if not EXAMPLE.exists():
        raise Stop(".env.example est introuvable : lancer le script depuis le dossier du dépôt")
    if ENV.exists() and not reconfigure:
        return complete_env(), False
    current = read_env(ENV) if ENV.exists() else {}

    print("\nConfiguration du .env")
    values = dict(current)
    values["PUID"], values["PGID"] = str(os.getuid()), str(os.getgid())
    for key in GENERATED:
        if not current.get(key):
            values[key] = secrets.token_hex(32)
    values["HERMES_DASHBOARD_BASIC_AUTH_USERNAME"] = ask(
        "Utilisateur du Dashboard", current.get("HERMES_DASHBOARD_BASIC_AUTH_USERNAME") or "admin")
    if not (current.get("HERMES_DASHBOARD_BASIC_AUTH_PASSWORD") and ask_yes("Garder le mot de passe du Dashboard ?")):
        values["HERMES_DASHBOARD_BASIC_AUTH_PASSWORD"] = ask_password()
    values.update(ask_llm_keys(current))
    values.update(ask_telegram(current))
    cpus = os.cpu_count() or 1
    values["HERMES_CPU_LIMIT"] = ask("Plafond de processeurs pour Hermes", current.get("HERMES_CPU_LIMIT") or str(min(2, cpus)))
    values["HERMES_MEM_LIMIT"] = ask("Plafond de mémoire pour Hermes (ex. 2G)", current.get("HERMES_MEM_LIMIT") or "2G")

    if ENV.exists():
        shutil.copy2(ENV, ENV.with_name(".env.bak"))
        os.chmod(ENV.with_name(".env.bak"), 0o600)
    write_env(render_env(EXAMPLE.read_text(encoding="utf-8"), values))
    ok(f".env écrit (PUID={values['PUID']}, PGID={values['PGID']}, clé de l'API générée, lisible par toi seul)")
    return read_env(ENV), not current


# ── 3. Le démarrage ───────────────────────────────────────────────────────────────────────────────────


def dashboard_status(port: str) -> dict | None:
    """L'état public du Dashboard (`/api/status`), ou None s'il ne répond pas encore."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=10) as r:
            return json.loads(r.read().decode("utf-8"))
    except (OSError, ValueError):
        return None


def start(values: dict[str, str]) -> None:
    if run(["docker", "compose", "config", "--quiet"]).returncode != 0:
        raise Stop("`docker compose config` refuse le fichier : relancer la commande pour voir l'erreur")
    ok("docker-compose.yml valide")
    print("\nDémarrage (le premier téléchargement de l'image peut prendre quelques minutes)…")
    if run(["docker", "compose", "up", "-d"], capture=False).returncode != 0:
        raise Stop("`docker compose up -d` a échoué")
    wait_ready(values)


def wait_ready(values: dict[str, str]) -> None:
    port = values.get("HERMES_DASHBOARD_PORT") or "9119"
    deadline = time.monotonic() + HEALTH_TIMEOUT
    state = ""
    while time.monotonic() < deadline:
        state = run(["docker", "inspect", "-f", "{{.State.Status}} {{.State.Health.Status}}", CONTAINER]).stdout.strip()
        status = dashboard_status(port)
        if state.startswith("running") and status is not None:
            ok("Hermes démarré")
            providers = status.get("auth_providers") or []
            if status.get("auth_required") is True and providers:
                ok(f"le Dashboard (port {port}) exige une connexion ({', '.join(providers)})")
            else:
                warn(f"le Dashboard (port {port}) est ouvert sans connexion : vérifier HERMES_DASHBOARD_BASIC_AUTH_*")
            if state.endswith("unhealthy"):
                warn(f"état Docker : {state} (voir `docker compose logs --tail 60 hermes`)")
            return
        time.sleep(5)
    raise Stop(f"Hermes ne répond pas après {HEALTH_TIMEOUT} s (état : {state or 'inconnu'}) : "
               "voir `docker compose logs --tail 60 hermes`")


# ── 4. Les réglages ───────────────────────────────────────────────────────────────────────────────────


def read_reglages() -> list[tuple[str, str]]:
    reglages = []
    for line in REGLAGES.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            key, _, value = line.partition(" ")
            reglages.append((key, value.strip()))
    return reglages


def apply_reglages(values: dict[str, str]) -> None:
    if not REGLAGES.exists():
        warn("reglages.conf introuvable : aucun réglage appliqué")
        return
    print()
    failed = 0
    for key, value in read_reglages():
        done = run(["docker", "compose", "exec", "-T", CONTAINER, "hermes", "config", "set", key, value])
        if done.returncode == 0:
            ok(f"réglage {key} = {value}")
        else:
            failed += 1
            fail(f"réglage {key} = {value} : {(done.stderr or done.stdout).strip()[:200]}")
    print("\nRedémarrage pour prendre les réglages en compte…")
    if run(["docker", "compose", "restart", CONTAINER]).returncode != 0:
        raise Stop("`docker compose restart` a échoué")
    wait_ready(values)
    if failed:
        raise Stop(f"{failed} réglage(s) non appliqué(s) : vérifier la clé dans la documentation de Hermes")


# ── 5. Le modèle ──────────────────────────────────────────────────────────────────────────────────────


def choose_model() -> None:
    print("\nLe modèle se choisit avec l'assistant de Hermes (fournisseur, puis modèle).")
    if ask_yes("Lancer maintenant `hermes model` dans le conteneur ?"):
        run(["docker", "compose", "exec", CONTAINER, "hermes", "model"], capture=False)
    else:
        print("  Plus tard : docker compose exec hermes hermes model")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Installe ou met à jour Hermes (Docker).")
    parser.add_argument("--reconfigurer", action="store_true", help="reposer toutes les questions du .env")
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        fail("le script pose des questions : le lancer dans un terminal")
        return 1
    print("=== Installation de Hermes ===\n")
    try:
        check_system()
        values, created = configure_env(args.reconfigurer)
        print()
        check_ports(values)
        check_memory(values)
        start(values)
        apply_reglages(values)
        if created:
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
