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
#                        Nom en minuscules avec tirets ; jamais d'écrasement ; 1 Mo au plus. Sans Claude Code.
#   claude               ouvre une conversation avec Claude Code dans le vault ; la demande de l'utilisateur arrive
#                        sur l'entrée standard. Claude Code lit lui-même les règles et les skills du vault
#                        (/triage, /commit…) : Hermes ne fait que transmettre.
#   suite                continue la dernière conversation (la réponse de l'utilisateur sur l'entrée standard)
# Toute autre demande est refusée. Claude Code est lancé puis s'arrête : rien ne tourne entre deux demandes, la
# conversation est gardée sur le disque du compte.

set -euo pipefail
VAULT="@VAULT@"  # remplacé à l'installation par le chemin du clone du vault
TAILLE_MAX=1048576
DEMANDE_MAX=65536
umask 002  # les fichiers créés restent modifiables par le groupe qui partage le vault

# Ce que Claude Code peut faire dans le vault, et ce qui lui est interdit même s'il le demande.
OUTILS="Read,Grep,Glob,Edit,Write,Skill,Bash(git:*),Bash(pwsh:*),Bash(rm:*),Bash(mv:*),Bash(mkdir:*)"
INTERDITS="Bash(git push --force:*),Bash(git push -f:*),Bash(git push --force-with-lease:*)"
CONSIGNE="Tu es lancé à distance par Hermes, l'assistant de l'utilisateur, qui te transmet ses demandes et lui \
relaie tes réponses : aucun dialogue direct, l'outil AskUserQuestion ne fonctionne pas. Quand une étape demande un \
choix sur le contenu du vault (où ranger, garder ou jeter), arrête-toi et termine ta réponse par la question, avec \
des choix numérotés ; sa réponse arrivera dans la suite de cette conversation. Ne lui pose jamais de question sur git : \
la mécanique est à toi. Réponses courtes : elles sont lues sur un téléphone. \
Mener chaque tâche jusqu'au bout, sans rien laisser à faire à l'utilisateur : \
- supprimer ou déplacer un fichier toi-même : git rm -f / git mv pour un fichier suivi, sinon git add puis git rm -f, \
ou rm / mv ; \
- quand la tâche a modifié le vault, la terminer par un commit (format du skill /commit ; la demande de l'utilisateur \
vaut confirmation, ne pas lui faire valider le message) qui ne contient que tes changements : ne jamais commiter \
.obsidian/ (réglages de l'Obsidian du serveur) ni ce que tu n'as pas modifié ; \
- puis pousser : git pull --rebase --autostash, puis git push. Jamais de push forcé. Seulement si un vrai conflit \
reste après le pull : git rebase --abort, et le signaler en une ligne (le commit reste fait sur le serveur)."

refuser() { echo "refusé : $1" >&2; exit 2; }

lire_demande() {
  local texte
  texte="$(head -c $((DEMANDE_MAX + 1)))"
  [[ -n "${texte//[[:space:]]/}" ]] || refuser "demande vide (elle arrive sur l'entrée standard)"
  [[ ${#texte} -le $DEMANDE_MAX ]] || refuser "demande de plus de 64 Ko"
  printf '%s' "$texte"
}

lancer_claude() {
  # L'environnement du compte (PATH de Claude Code, modèle par défaut) : SSH n'ouvre pas de session de connexion.
  set +u
  # shellcheck disable=SC1091
  source "$HOME/.profile" > /dev/null 2>&1 || true
  set -u
  # Le chemin réel, sans lien symbolique : Claude Code n'accepte de supprimer que dans son dossier de travail, et
  # compare des chemins réels.
  cd "$(realpath "$VAULT")"
  exec claude "$@" --allowedTools "$OUTILS" --disallowedTools "$INTERDITS" --append-system-prompt "$CONSIGNE"
}

read -r -a mots <<< "${SSH_ORIGINAL_COMMAND:-}"
action="${mots[0]:-aide}"

case "$action" in
  aide)
    echo "Actions : aide ; inbox <nom>.md (la note sur l'entrée standard) ; claude (la demande sur l'entrée standard) ;"
    echo "suite (la réponse sur l'entrée standard, dans la dernière conversation)"
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

  claude)
    [[ ${#mots[@]} -eq 1 ]] || refuser "claude ne prend aucun argument : la demande arrive sur l'entrée standard"
    demande="$(lire_demande)"
    lancer_claude -p "$demande"
    ;;

  suite)
    [[ ${#mots[@]} -eq 1 ]] || refuser "suite ne prend aucun argument : la réponse arrive sur l'entrée standard"
    reponse="$(lire_demande)"
    lancer_claude --continue -p "$reponse"
    ;;

  *)
    refuser "action inconnue ($action). Actions : aide, inbox, claude, suite"
    ;;
esac
