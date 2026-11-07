"""Les vérifications : Linux, Docker, Compose v2, démon joignable, ports libres, mémoire disponible."""

from __future__ import annotations

import re
import shutil
import socket
import sys
from pathlib import Path

from installation.commun import CONTAINER, Stop, ok, run, warn


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
