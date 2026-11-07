# Le lien entre Hermes et le vault

Quand tu le lui demandes (sur Telegram, par exemple), Hermes **dépose une note dans l'Inbox du vault**, ou
**transmet ta demande à Claude Code**, lancé dans le vault : trier l'Inbox, commiter, pousser, chercher une note…
Claude Code connaît le vault (son `CLAUDE.md`, ses règles, ses skills `/triage`, `/commit`…) ; Hermes ne fait que
relayer, dans les deux sens. Il ne peut rien faire d'autre sur le serveur.

## Le processus

1. Tu demandes à Hermes, par exemple : « fais le tri du vault ».
2. Hermes lance Claude Code dans le vault, avec ta demande telle quelle (action `claude`).
3. Claude Code fait le travail avec les skills du vault.
4. S'il a besoin de ton avis, Hermes te relaie sa question ; ta réponse repart dans la même conversation (action
   `suite`).
5. Hermes te donne le résultat.

La mécanique git appartient au vault, pas au gardien : Claude Code suit les procédures du vault. Le tri (`/triage`)
fait toujours récupérer (`git pull`), trier, commiter, pousser, sur le serveur comme sur le PC. Les captures de
l'Inbox ne sont pas versionnées : elles n'entrent dans git qu'une fois triées.

Claude Code est lancé à chaque demande, puis s'arrête : rien ne tourne entre deux demandes, et la conversation est
gardée sur le disque du compte du vault. Chaque demande et chaque réponse appellent le modèle : elles sont payantes.

## Installer

Prérequis : le vault installé sur ce serveur par son propre script (`python3 .serveur/install.py`, options
`--vault` puis `--acces`), et Hermes démarré. Puis, dans ce dépôt, sur le serveur :

```bash
git pull && python3 install.py --vault
```

Sans question : le clone du vault, le port SSH et le réseau Docker de Hermes sont lus sur la machine. Il se termine
par une vérification : `aide` répond, une commande quelconque est refusée. À relancer si le réseau Docker de Hermes
change (après un `docker compose down`, par exemple) : la clé n'est acceptée que depuis ce réseau.

## Comment ça marche

Trois pièces, une par endroit :

| Où | Quoi | Rôle |
|---|---|---|
| Dans le conteneur de Hermes (`data/home/.ssh/`) | Sa **clé privée** `id_vault`, sa configuration SSH (l'hôte `vault`) | Ce que Hermes présente pour entrer |
| Sur le serveur, dans le compte du vault (`~/.ssh/authorized_keys`) | La **clé publique** de Hermes, avec ses restrictions | Qui a le droit d'entrer, et pour faire quoi |
| Sur le serveur (`/usr/local/bin/hermes-vault`, à root) | La **commande imposée** (source : `installation/hermes-vault.sh`) | La seule chose qui s'exécute à l'entrée |

Le skill `vault` (source : `skills/vault/SKILL.md`, copié dans `data/skills/`) apprend à Hermes à transmettre ses demandes
sur le vault, et le format des notes qu'il dépose.

## La sécurité, point par point

**Une clé SSH, c'est une paire.** La clé **privée** reste chez celui qui se connecte (Hermes, dans son conteneur) et
ne sort jamais. La clé **publique** se dépose chez celui qui accepte la connexion (le compte du vault). À la
connexion, le serveur vérifie que l'arrivant possède la clé privée qui correspond, sans qu'elle circule. Aucun mot de
passe n'intervient.

**Le compte du vault n'a pas de mot de passe.** Personne ne peut donc s'y connecter en tapant un mot de passe, ni en
SSH, ni sur la machine. Seules deux portes existent : `sudo -iu` depuis le compte d'administration, et une clé
publique déposée dans son `authorized_keys`. Ce lien ouvre la seconde, pour la seule clé de Hermes.

**La clé de Hermes est bridée dans `authorized_keys`**, sur sa ligne même :

- `command="/usr/local/bin/hermes-vault"` : quoi que Hermes demande, c'est cette commande qui s'exécute ; sa demande
  n'est qu'un texte qu'elle lit (`SSH_ORIGINAL_COMMAND`) et compare à la liste des actions permises. Pas de shell :
  `rm`, `cat`, `id`… sont refusés.
- `restrict` : ni terminal, ni transfert de ports, ni tunnel, ni agent SSH.
- `from="<réseau Docker de Hermes>"` : la clé n'est acceptée que depuis le réseau du conteneur. Volée et utilisée
  ailleurs, elle ne sert à rien.

**La commande imposée appartient à root.** Le compte du vault ne peut pas la modifier, donc pas élargir ce qu'elle
permet. Elle refuse tout nom de note hors du format (minuscules, tirets, `.md`), n'écrase jamais une note, et limite
une note à 1 Mo.

**Ce que Hermes peut faire, au pire.** Déposer des notes dans l'Inbox, et faire faire à Claude Code, sous le compte
du vault, ce que ses outils permettent : lire, modifier, déplacer et supprimer les fichiers, git (sans push forcé), PowerShell (la carte
du vault). Le compte du vault n'a pas `sudo`, et ne voit que le vault (groupe commun, voir le script du vault). Une
erreur sur le vault se répare : git garde tout l'historique, et le push forcé, qui pourrait l'effacer sur GitHub,
est interdit.

**Ce qui ne change pas.** Ton accès SSH au serveur, tes clés, ton compte : ce lien n'y touche pas. La règle de pare-feu
ajoutée n'accepte SSH que depuis le réseau Docker de Hermes.

## Retirer le lien

Supprimer la ligne terminée par `hermes-vault` dans `authorized_keys` du compte du vault suffit : la clé de Hermes
n'ouvre plus rien. Puis, pour tout nettoyer : `sudo rm /usr/local/bin/hermes-vault`, la règle UFW commentée « SSH,
Hermes vers le vault » (`sudo ufw status numbered`, puis `sudo ufw delete <numéro>`), et le dossier
`data/skills/vault`.
