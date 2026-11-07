"""Les réglages : chaque ligne de reglages.conf appliquée avec `hermes config set`, puis un redémarrage.

data/config.yaml, qui appartient à Hermes, n'est jamais réécrit.
"""

from __future__ import annotations

from installation.commun import CONTAINER, ROOT, Stop, fail, ok, run, warn
from installation.demarrage import wait_ready

REGLAGES = ROOT / "reglages.conf"


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
