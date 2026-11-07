#!/usr/bin/env python3
"""Installe ou met à jour Hermes sur un serveur Linux, avec Docker.

Usage, depuis le dossier du dépôt, sur le serveur :
    python3 install.py                  première installation, ou mise à jour après un `git pull`
    python3 install.py --reconfigurer   reposer toutes les questions du .env
    python3 install.py --pare-feu       mettre en place le pare-feu du serveur (docs/pare-feu-serveur.md)
    python3 install.py --help           la liste des options

Sans option, dans l'ordre, une ligne OK, ÉCHEC ou ATTENTION par point :
1. les vérifications : Linux, Docker, Compose v2, démon joignable, ports libres, mémoire disponible ;
2. le .env :
   - absent : créé depuis .env.example, en posant les questions (UID et GID de l'utilisateur, clés générées,
     mot de passe du Dashboard, clés des modèles, Telegram, plafonds de ressources) ;
   - présent : jamais réécrit. Seules les variables apparues dans .env.example sont ajoutées à la fin (une question
     pour chaque secret, une clé tirée au hasard pour les clés générées, la valeur d'exemple pour le reste), après
     une copie de sauvegarde .env.bak ;
3. le démarrage : `docker compose config`, `docker compose up -d`, puis l'attente du Dashboard ;
4. les réglages : chaque ligne de reglages.conf appliquée avec `hermes config set`, puis un redémarrage ;
5. le modèle, à la première installation seulement : propose l'assistant `hermes model`.

Chaque étape est un fichier de installation/, et chaque option aussi : ajouter une option, c'est écrire un fichier
installation/<nom>.py qui expose `executer()`, puis ajouter sa ligne dans OPTIONS.

Aucun secret n'est affiché ni passé en ligne de commande ; le .env est créé lisible par son seul propriétaire.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from installation.commun import Stop, fail

DEFAUT = "installer"  # sans option : installation/installer.py
OPTIONS = {  # option → fichier de installation/ qui la réalise
    "--reconfigurer": "reconfigurer",
    "--pare-feu": "pare_feu",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Installe ou met à jour Hermes (Docker).")
    choix = parser.add_mutually_exclusive_group()
    for option, nom in OPTIONS.items():
        aide = (importlib.import_module(f"installation.{nom}").__doc__ or "").strip().splitlines()[0]
        choix.add_argument(option, dest="option", action="store_const", const=nom, help=aide)
    args = parser.parse_args(argv)
    if not sys.stdin.isatty():
        fail("le script pose des questions : le lancer dans un terminal")
        return 1
    print("=== Installation de Hermes ===\n" if not args.option else f"=== install.py --{args.option.replace('_', '-')} ===\n")
    try:
        importlib.import_module(f"installation.{args.option or DEFAUT}").executer()
    except Stop as e:
        fail(str(e))
        return 1
    except KeyboardInterrupt:
        print()
        fail("interrompu")
        return 130
    if not args.option:
        print("\nÀ vérifier ensuite : `docker stats --no-stream hermes`, et un message à ton bot Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
