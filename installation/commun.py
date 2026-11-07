"""Ce que partagent les étapes : l'affichage OK / ÉCHEC / ATTENTION, les questions, le lancement des commandes."""

from __future__ import annotations

import getpass
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # le dossier du dépôt
CONTAINER = "hermes"


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


def ask(question: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"  {question}{suffix} : ").strip()
    return answer or default


def ask_yes(question: str, default: bool = True) -> bool:
    answer = input(f"  {question} [{'O/n' if default else 'o/N'}] : ").strip().lower()
    return default if not answer else answer in ("o", "oui", "y", "yes")


def ask_secret(question: str) -> str:
    return getpass.getpass(f"  {question} (rien ne s'affiche) : ").strip()
