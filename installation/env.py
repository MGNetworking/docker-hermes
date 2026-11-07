"""Le .env : créé en posant les questions, complété sans jamais être réécrit, ou reconfiguré à la demande."""

from __future__ import annotations

import os
import re
import secrets
import shutil
import time
from pathlib import Path

from installation.commun import ROOT, Stop, ask, ask_secret, ask_yes, ok

ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"
LLM_KEYS = ["DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY"]
GENERATED = {"API_SERVER_KEY", "HERMES_DASHBOARD_BASIC_AUTH_SECRET"}  # clés tirées au hasard, jamais demandées
SECRETS = {*LLM_KEYS, *GENERATED, "HERMES_DASHBOARD_BASIC_AUTH_PASSWORD", "TELEGRAM_BOT_TOKEN"}

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


def backup_env() -> None:
    backup = ENV.with_name(".env.bak")
    shutil.copy2(ENV, backup)
    os.chmod(backup, 0o600)


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
    backup_env()
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
        backup_env()
    write_env(render_env(EXAMPLE.read_text(encoding="utf-8"), values))
    ok(f".env écrit (PUID={values['PUID']}, PGID={values['PGID']}, clé de l'API générée, lisible par toi seul)")
    return read_env(ENV), not current
