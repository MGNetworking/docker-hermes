"""Installer ou mettre à jour Hermes : vérifications, .env, démarrage, réglages, et le modèle à la première installation."""

from __future__ import annotations

from installation.demarrage import start
from installation.env import configure_env
from installation.modele import choose_model
from installation.reglages import apply_reglages
from installation.verifications import check_memory, check_ports, check_system


def executer(reconfigurer: bool = False) -> None:
    check_system()
    values, created = configure_env(reconfigurer)
    print()
    check_ports(values)
    check_memory(values)
    start(values)
    apply_reglages(values)
    if created:
        choose_model()
