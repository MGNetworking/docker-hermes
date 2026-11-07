"""Relier Hermes au vault : sa clé SSH n'ouvre, sous le compte du vault, que la commande hermes-vault.

Sans question : tout est lu sur la machine.

Lu sur la machine :
- le clone du vault : celui que le compte du vault accepte dans git (safe.directory, réglé par l'option --acces du
  script du vault) ;
- le port SSH : `sshd -T` ;
- le réseau Docker de Hermes : `docker inspect`.

Dans l'ordre, une ligne OK, ÉCHEC ou ATTENTION par point :
1. le conteneur hermes joint le serveur (host.docker.internal, extra_hosts du compose) ;
2. la clé SSH de Hermes, créée dans son conteneur (/opt/data/home/.ssh, donc dans data/) ;
3. la commande hermes-vault (installation/hermes-vault.sh), copiée dans /usr/local/bin, propriété de root ;
4. l'authorized_keys du compte du vault : la clé de Hermes, réduite à hermes-vault (command=…), sans transfert ni
   terminal (restrict), acceptée seulement depuis le réseau Docker de Hermes (from=…) ;
5. le pare-feu : SSH accepté depuis le réseau Docker de Hermes ;
6. la configuration SSH de Hermes et l'empreinte du serveur ;
7. le skill vault (skills/vault/SKILL.md), copié dans data/skills ;
8. la vérification : `aide` répond, une commande quelconque est refusée.

Relancé, il remplace la clé autorisée de Hermes (une seule ligne, jamais doublée) et refait la vérification. À
relancer si le réseau Docker de Hermes change (après un `docker compose down`, par exemple).
"""

from __future__ import annotations

import ipaddress
import json
import subprocess

from installation.commun import CONTAINER, ROOT, Stop, ok, run, warn
from installation.pare_feu import port_ssh, sudo

COMPTE = "vault"  # le compte du vault sur le serveur (créé par le script du vault)
COMMANDE = "/usr/local/bin/hermes-vault"
SOURCE_COMMANDE = ROOT / "installation" / "hermes-vault.sh"
SKILL = ROOT / "skills" / "vault" / "SKILL.md"
HOTE = "host.docker.internal"
SSH_HERMES = "/opt/data/home/.ssh"  # le dossier SSH des outils de Hermes, dans son volume data/
CLE = f"{SSH_HERMES}/id_vault"
REPERE = "hermes-vault"  # le commentaire de la clé : repère sa ligne dans authorized_keys


def dans_hermes(commande: str, entree: str = "") -> subprocess.CompletedProcess[str]:
    """Une commande shell dans le conteneur, sous l'utilisateur hermes : les fichiers créés lui appartiennent."""
    return subprocess.run(["docker", "exec", "-i", "-u", "hermes", CONTAINER, "sh", "-c", commande],
                          input=entree, capture_output=True, text=True, check=False)


# ── Ce qui se lit sur la machine ──────────────────────────────────────────────────────────────────────


def clone_du_vault() -> str:
    if subprocess.run(["id", COMPTE], capture_output=True, check=False).returncode != 0:
        raise Stop(f"le compte {COMPTE} n'existe pas : lancer d'abord le script du vault (--vault, puis --acces)")
    lu = sudo("-iu", COMPTE, "git", "config", "--global", "--get-all", "safe.directory")
    clones = [d for d in lu.stdout.split() if sudo("test", "-f", f"{d}/.serveur/install.py").returncode == 0]
    if not clones:
        raise Stop(f"aucun clone du vault accessible au compte {COMPTE} : lancer l'option --acces du script du vault")
    if len(clones) > 1:
        raise Stop(f"plusieurs clones du vault déclarés pour le compte {COMPTE} : {', '.join(clones)}")
    return clones[0]


def reseau_hermes() -> ipaddress.IPv4Network:
    lu = run(["docker", "inspect", "-f", "{{json .NetworkSettings.Networks}}", CONTAINER])
    if lu.returncode != 0:
        raise Stop("le conteneur hermes ne tourne pas : python3 install.py, puis relancer")
    for nom in json.loads(lu.stdout):
        detail = run(["docker", "network", "inspect", "-f", "{{json .IPAM.Config}}", nom])
        for bloc in json.loads(detail.stdout or "[]") or []:
            sous_reseau = bloc.get("Subnet", "")
            if sous_reseau and ":" not in sous_reseau:
                return ipaddress.ip_network(sous_reseau)
    raise Stop("réseau Docker de Hermes introuvable (`docker inspect`)")


# ── Les étapes ────────────────────────────────────────────────────────────────────────────────────────


def joindre_le_serveur() -> None:
    hotes = run(["docker", "inspect", "-f", "{{json .HostConfig.ExtraHosts}}", CONTAINER]).stdout
    if HOTE in hotes:
        ok(f"le conteneur joint le serveur ({HOTE})")
        return
    print(f"Le conteneur ne connaît pas encore {HOTE} : redémarrage avec le compose à jour…")
    if run(["docker", "compose", "up", "-d"], capture=False).returncode != 0:
        raise Stop("`docker compose up -d` a échoué")
    if HOTE not in run(["docker", "inspect", "-f", "{{json .HostConfig.ExtraHosts}}", CONTAINER]).stdout:
        raise Stop(f"{HOTE} absent du conteneur : git pull dans ce dépôt (extra_hosts du compose), puis relancer")
    ok(f"conteneur redémarré : il joint le serveur ({HOTE})")


def cle_de_hermes() -> str:
    if dans_hermes(f"test -f {CLE}").returncode != 0:
        cree = dans_hermes(f"mkdir -p {SSH_HERMES} && chmod 700 {SSH_HERMES} && "
                           f"ssh-keygen -q -t ed25519 -N '' -C {REPERE} -f {CLE}")
        if cree.returncode != 0:
            raise Stop(f"création de la clé SSH de Hermes impossible : {cree.stderr.strip()[:300]}")
        ok("clé SSH de Hermes créée, dans son conteneur (data/home/.ssh)")
    else:
        ok("clé SSH de Hermes déjà présente")
    publique = dans_hermes(f"cat {CLE}.pub").stdout.split()
    if len(publique) < 2:
        raise Stop("clé publique de Hermes illisible")
    return f"{publique[0]} {publique[1]} {REPERE}"


def installer_commande(vault: str) -> None:
    texte = SOURCE_COMMANDE.read_text(encoding="utf-8").replace("\r\n", "\n").replace("@VAULT@", vault)
    if sudo("tee", COMMANDE, entree=texte).returncode != 0:
        raise Stop(f"écriture de {COMMANDE} impossible")
    if sudo("chown", "root:root", COMMANDE).returncode != 0 or sudo("chmod", "755", COMMANDE).returncode != 0:
        raise Stop(f"droits de {COMMANDE} impossibles à régler")
    ok(f"commande {COMMANDE} installée (propriété de root, le compte {COMPTE} ne peut pas la modifier)")


def autoriser(cle: str, reseau: ipaddress.IPv4Network) -> None:
    import pwd  # Linux seulement : importé ici pour que --help marche partout

    dossier = pwd.getpwnam(COMPTE).pw_dir
    fichier = f"{dossier}/.ssh/authorized_keys"
    lu = sudo("cat", fichier)
    lignes = [l for l in (lu.stdout.splitlines() if lu.returncode == 0 else []) if not l.rstrip().endswith(REPERE)]
    lignes.append(f'restrict,from="{reseau}",command="{COMMANDE}" {cle}')
    if sudo("-u", COMPTE, "mkdir", "-p", "-m", "700", f"{dossier}/.ssh").returncode != 0:
        raise Stop(f"création de ~/.ssh du compte {COMPTE} impossible")
    if sudo("tee", fichier, entree="\n".join(lignes) + "\n").returncode != 0:
        raise Stop(f"écriture de authorized_keys du compte {COMPTE} impossible")
    sudo("chown", f"{COMPTE}:{COMPTE}", fichier)
    sudo("chmod", "600", fichier)
    ok(f"clé de Hermes autorisée sous {COMPTE} : hermes-vault seulement, depuis le réseau de Hermes seulement")


def pare_feu(reseau: ipaddress.IPv4Network, ssh: str) -> None:
    if not run(["sh", "-c", "command -v ufw"]).stdout.strip():
        warn("ufw absent : aucune règle ajoutée ; si un pare-feu filtre SSH, l'ouvrir depuis le réseau de Hermes")
        return
    regle = ("ufw", "allow", "from", str(reseau), "to", "any", "port", ssh, "proto", "tcp",
             "comment", "SSH, Hermes vers le vault")
    if sudo(*regle).returncode != 0:
        raise Stop("ajout de la règle SSH pour Hermes au pare-feu impossible")
    ok("pare-feu : SSH accepté depuis le réseau de Hermes")


def configurer_ssh(ssh: str) -> None:
    config = (f"Host vault\n  HostName {HOTE}\n  Port {ssh}\n  User {COMPTE}\n  IdentityFile {CLE}\n"
              f"  IdentitiesOnly yes\n  UserKnownHostsFile {SSH_HERMES}/known_hosts\n  StrictHostKeyChecking yes\n")
    if dans_hermes(f"cat > {SSH_HERMES}/config && chmod 600 {SSH_HERMES}/config", entree=config).returncode != 0:
        raise Stop("écriture de la configuration SSH de Hermes impossible")
    empreinte = dans_hermes(f"ssh-keyscan -p {ssh} -t ed25519 {HOTE} 2>/dev/null")
    if empreinte.returncode != 0 or not empreinte.stdout.strip():
        raise Stop(f"le serveur ne répond pas en SSH depuis le conteneur ({HOTE}, port {ssh}) : sshd écoute-t-il "
                   f"sur toutes les adresses ? (`sudo sshd -T | grep listenaddress`)")
    if dans_hermes(f"cat > {SSH_HERMES}/known_hosts", entree=empreinte.stdout).returncode != 0:
        raise Stop("écriture de l'empreinte du serveur impossible")
    ok("configuration SSH de Hermes écrite (hôte « vault »), empreinte du serveur enregistrée")


def installer_skill() -> None:
    texte = SKILL.read_text(encoding="utf-8")
    if dans_hermes("mkdir -p /opt/data/skills/vault && cat > /opt/data/skills/vault/SKILL.md",
                   entree=texte).returncode != 0:
        raise Stop("copie du skill vault impossible")
    ok("skill vault installé (data/skills/vault)")


def verifier() -> None:
    ssh = f"ssh -F {SSH_HERMES}/config -o BatchMode=yes vault"
    aide = dans_hermes(f"{ssh} aide")
    if aide.returncode != 0 or "inbox" not in aide.stdout:
        raise Stop(f"Hermes ne joint pas le vault : {(aide.stderr or aide.stdout).strip()[:300]}")
    ok("Hermes joint le vault : `aide` répond")
    autre = dans_hermes(f"{ssh} id")
    if autre.returncode == 0:
        raise Stop("une commande quelconque passe : la restriction command=… n'est pas appliquée")
    ok("toute autre commande est refusée")


def executer() -> None:
    print("Le mot de passe sudo peut être demandé.")
    if subprocess.run(["sudo", "-v"], check=False).returncode != 0:
        raise Stop("sudo refusé : rien n'a été modifié")
    vault = clone_du_vault()
    ssh = port_ssh()
    joindre_le_serveur()
    reseau = reseau_hermes()
    ok("clone du vault, port SSH et réseau de Hermes lus sur la machine")

    cle = cle_de_hermes()
    installer_commande(vault)
    autoriser(cle, reseau)
    pare_feu(reseau, ssh)
    configurer_ssh(ssh)
    installer_skill()
    verifier()
    print("\nÀ essayer sur Telegram : « garde dans mon vault l'idée suivante : … ». La note arrive dans 00 - Inbox.")
