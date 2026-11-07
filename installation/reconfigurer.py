"""Reposer toutes les questions du .env (les valeurs existantes sont proposées), puis installer comme d'habitude."""

from __future__ import annotations

from installation import installer


def executer() -> None:
    installer.executer(reconfigurer=True)
