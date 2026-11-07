#!/bin/bash
# hermes-vault : la seule commande que la clé SSH de Hermes peut lancer sur le serveur.
#
# Installé par `python3 install.py --vault` dans /usr/local/bin, propriété de root : le compte du vault, sous lequel
# cette commande tourne, ne peut pas la modifier. Son authorized_keys l'impose (command=…) : quoi que Hermes demande,
# c'est ce script qui s'exécute, et la demande n'arrive que dans SSH_ORIGINAL_COMMAND.
#
# Actions :
#   aide                 la liste des actions (ne modifie rien)
#   inbox <nom>.md       dépose une note dans 00 - Inbox ; son contenu arrive sur l'entrée standard.
#                        Nom en minuscules avec tirets ; jamais d'écrasement ; 1 Mo au plus.
#   commit               lance /commit du vault avec Claude Code (git et la carte du vault seulement)
# Toute autre demande est refusée.

set -euo pipefail
VAULT="@VAULT@"  # remplacé à l'installation par le chemin du clone du vault
TAILLE_MAX=1048576
umask 002  # les fichiers créés restent modifiables par le groupe qui partage le vault

refuser() { echo "refusé : $1" >&2; exit 2; }

read -r -a mots <<< "${SSH_ORIGINAL_COMMAND:-}"
action="${mots[0]:-aide}"

case "$action" in
  aide)
    echo "Actions : aide ; inbox <nom>.md (contenu sur l'entrée standard) ; commit"
    ;;

  inbox)
    nom="${mots[1]:-}"
    [[ ${#mots[@]} -eq 2 && "$nom" =~ ^[a-z0-9][a-z0-9-]{0,80}\.md$ ]] \
      || refuser "inbox <nom-en-minuscules-avec-tirets>.md"
    cible="$VAULT/00 - Inbox/$nom"
    [[ ! -e "$cible" ]] || refuser "$nom existe déjà dans l'Inbox"
    temporaire="$cible.part"
    head -c $((TAILLE_MAX + 1)) > "$temporaire"
    if [[ $(stat -c %s "$temporaire") -gt $TAILLE_MAX ]]; then
      rm -f "$temporaire"
      refuser "note de plus de 1 Mo"
    fi
    mv -n "$temporaire" "$cible"
    echo "déposé : 00 - Inbox/$nom"
    ;;

  commit)
    [[ ${#mots[@]} -eq 1 ]] || refuser "commit ne prend aucun argument"
    # L'environnement du compte (PATH de Claude Code, modèle par défaut) : SSH n'ouvre pas de session de connexion.
    set +u
    # shellcheck disable=SC1091
    source "$HOME/.profile" > /dev/null 2>&1 || true
    set -u
    cd "$VAULT"
    exec claude --allowedTools "Bash(git:*),Bash(pwsh:*),Read,Grep,Glob" -p "/commit"
    ;;

  *)
    refuser "action inconnue ($action). Actions : aide, inbox, commit"
    ;;
esac
