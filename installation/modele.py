"""Le modèle : propose l'assistant `hermes model` (fournisseur, puis modèle)."""

from __future__ import annotations

from installation.commun import CONTAINER, ask_yes, run


def choose_model() -> None:
    print("\nLe modèle se choisit avec l'assistant de Hermes (fournisseur, puis modèle).")
    if ask_yes("Lancer maintenant `hermes model` dans le conteneur ?"):
        run(["docker", "compose", "exec", CONTAINER, "hermes", "model"], capture=False)
    else:
        print("  Plus tard : docker compose exec hermes hermes model")
