# Le lien entre Hermes et le vault

Hermes peut **déposer une note dans l'Inbox du vault** et **y lancer `/commit --auto`** (commit de l'Inbox, puis
push), quand tu le lui demandes (sur
Telegram, par exemple). Il ne peut rien faire d'autre sur le serveur.

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

Le skill `vault` (source : `skills/vault/SKILL.md`, copié dans `data/skills/`) apprend à Hermes les deux actions et
le format des notes.

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

**Ce que Hermes peut faire, au pire.** Déposer des notes dans l'Inbox, et lancer `/commit --auto`, qui commite l'Inbox seule et la pousse (jamais
`--force`), en faisant tourner Claude
Code sous le compte du vault avec les seuls outils git, PowerShell (la carte du vault) et la lecture. Le compte du
vault n'a pas `sudo`, et ne voit que le vault (groupe commun, voir le script du vault).

**Ce qui ne change pas.** Ton accès SSH au serveur, tes clés, ton compte : ce lien n'y touche pas. La règle de pare-feu
ajoutée n'accepte SSH que depuis le réseau Docker de Hermes.

## Retirer le lien

Supprimer la ligne terminée par `hermes-vault` dans `authorized_keys` du compte du vault suffit : la clé de Hermes
n'ouvre plus rien. Puis, pour tout nettoyer : `sudo rm /usr/local/bin/hermes-vault`, la règle UFW commentée « SSH,
Hermes vers le vault » (`sudo ufw status numbered`, puis `sudo ufw delete <numéro>`), et le dossier
`data/skills/vault`.
