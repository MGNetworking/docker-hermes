"""Le démarrage : `docker compose config`, `docker compose up -d`, puis l'attente du Dashboard et le contrôle de sa connexion."""

from __future__ import annotations

import json
import time
import urllib.request

from installation.commun import CONTAINER, Stop, ok, run, warn

HEALTH_TIMEOUT = 180  # secondes


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
