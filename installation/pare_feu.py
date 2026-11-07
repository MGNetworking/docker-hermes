"""Mettre en place le pare-feu du serveur (UFW et les ports Docker), sans question : tout est lu sur la machine.

Le pare-feu protège tout le serveur, pas seulement Hermes. Aucune valeur du réseau n'est écrite dans le dépôt.

Lu sur la machine :
- l'interface et le réseau local : la route par défaut et l'adresse de son interface ;
- le port SSH : `sshd -T` ;
- les ports publiés par les conteneurs : `docker ps`.

Règles :
- UFW : entrée refusée par défaut, sortie autorisée, SSH accepté depuis le réseau local ;
- Docker contourne UFW : les ports publiés se filtrent dans la chaîne DOCKER-USER, écrite dans /etc/ufw/after.rules
  pour être rechargée à chaque démarrage. Par défaut, chaque port publié est accepté depuis le réseau local.
- Facultatif : le fichier local pare-feu.local (jamais versionné, voir pare-feu.local.example) réserve des conteneurs
  au seul reverse proxy, ou les ferme.

Sécurité : une désactivation automatique est programmée avant l'activation, puis annulée seulement si la session
SSH en cours vient du réseau local autorisé et que la règle SSH est en place.
"""

from __future__ import annotations

import ipaddress
import os
import re
import subprocess

from installation.commun import ROOT, Stop, ask_yes, fail, ok, run, warn

AFTER_RULES = "/etc/ufw/after.rules"
SAUVEGARDE = "/etc/ufw/after.rules.avant-docker-user"
DEBUT = "# BEGIN DOCKER-USER (hermes/installation/pare_feu.py)"
FIN = "# END DOCKER-USER"
SECOURS = "pare-feu-secours"
DELAI_SECOURS = 180  # secondes
LOCAL = ROOT / "pare-feu.local"


def sudo(*args: str, entree: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sudo", *args], input=entree, capture_output=True, text=True, check=False)


# ── Ce qui se lit sur la machine ──────────────────────────────────────────────────────────────────────


def interface_et_reseau() -> tuple[str, ipaddress.IPv4Network]:
    route = run(["ip", "-4", "route", "show", "default"]).stdout.split()
    if "dev" not in route:
        raise Stop("aucune route par défaut : interface réseau introuvable")
    interface = route[route.index("dev") + 1]
    adresse = re.search(r"inet (\d+\.\d+\.\d+\.\d+/\d+)", run(["ip", "-4", "-o", "addr", "show", "dev", interface]).stdout)
    if not adresse:
        raise Stop(f"aucune adresse IPv4 sur l'interface {interface}")
    return interface, ipaddress.ip_interface(adresse.group(1)).network


def port_ssh() -> str:
    for ligne in sudo("sshd", "-T").stdout.splitlines():
        if ligne.startswith("port "):
            return ligne.split()[1]
    raise Stop("port d'écoute de sshd introuvable (`sshd -T`) : rien n'a été modifié")


def ports_publies() -> dict[str, list[str]]:
    """Les ports TCP publiés sur la machine, par conteneur (une plage s'écrit début:fin)."""
    sortie = run(["docker", "ps", "--format", "{{.Names}}\t{{.Ports}}"])
    if sortie.returncode != 0:
        raise Stop("`docker ps` a échoué")
    publies: dict[str, list[str]] = {}
    for ligne in sortie.stdout.splitlines():
        nom, _, ports = ligne.partition("\t")
        vus: list[str] = []
        for publie in re.findall(r":(\d+(?:-\d+)?)->\d+(?:-\d+)?/tcp", ports):
            port = publie.replace("-", ":")
            if port not in vus:
                vus.append(port)
        if vus:
            publies[nom] = vus
    return publies


def lire_local(reseau: ipaddress.IPv4Network) -> tuple[str | None, set[str], set[str]]:
    """pare-feu.local : l'adresse du reverse proxy, les conteneurs qui lui sont réservés, les conteneurs fermés."""
    if not LOCAL.exists():
        return None, set(), set()
    valeurs: dict[str, str] = {}
    for ligne in LOCAL.read_text(encoding="utf-8").splitlines():
        ligne = ligne.split("#", 1)[0].strip()
        if "=" in ligne:
            cle, _, valeur = ligne.partition("=")
            valeurs[cle.strip()] = valeur.strip()
    proxy = valeurs.get("reverse_proxy") or None
    reserves = set(valeurs.get("via_reverse_proxy", "").split())
    fermes = set(valeurs.get("fermes", "").split())
    if reserves and not proxy:
        raise Stop("pare-feu.local réserve des conteneurs au reverse proxy sans donner son adresse (reverse_proxy = …)")
    if proxy:
        try:
            if ipaddress.ip_address(proxy) not in reseau:
                raise Stop(f"pare-feu.local : le reverse proxy n'est pas dans le réseau local ({reseau})")
        except ValueError:
            raise Stop("pare-feu.local : reverse_proxy n'est pas une adresse IPv4") from None
    return proxy, reserves, fermes


# ── Les règles ────────────────────────────────────────────────────────────────────────────────────────


def regles(interface: str, reseau: str, proxy: str | None, par_proxy: list[str], en_local: list[str]) -> list[str]:
    lignes = [
        "-A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN",
        f"-A DOCKER-USER ! -i {interface} -j RETURN",
    ]
    # Une adresse seule s'écrit /32 : c'est la forme qu'affiche `iptables -S`, comparée à la vérification.
    lignes += [f"-A DOCKER-USER -s {proxy}/32 -p tcp -m conntrack --ctorigdstport {p} -j RETURN" for p in par_proxy]
    lignes += [f"-A DOCKER-USER -s {reseau} -p tcp -m conntrack --ctorigdstport {p} -j RETURN" for p in en_local]
    lignes.append(f"-A DOCKER-USER -i {interface} -j DROP")
    return lignes


def bloc(lignes: list[str]) -> str:
    return "\n".join(["", DEBUT, "*filter", ":DOCKER-USER - [0:0]", *lignes, "COMMIT", FIN, ""])


def sans_bloc(texte: str) -> str:
    """after.rules sans un éventuel bloc DOCKER-USER déjà posé (pour le remplacer, jamais le doubler)."""
    return re.sub(r"\n*# BEGIN DOCKER-USER[^\n]*\n.*?# END DOCKER-USER\n?", "\n", texte, flags=re.S)


# ── L'application ─────────────────────────────────────────────────────────────────────────────────────


def appliquer(reseau: str, ssh: str, lignes: list[str]) -> None:
    lu = sudo("cat", AFTER_RULES)
    if lu.returncode != 0:
        raise Stop(f"lecture de {AFTER_RULES} impossible : {lu.stderr.strip()}")
    if sudo("test", "-e", SAUVEGARDE).returncode != 0:
        if sudo("cp", AFTER_RULES, SAUVEGARDE).returncode != 0:
            raise Stop(f"sauvegarde de {AFTER_RULES} impossible : rien n'a été modifié")
        ok(f"sauvegarde : {SAUVEGARDE}")
    for commande in (("ufw", "default", "deny", "incoming"), ("ufw", "default", "allow", "outgoing"),
                     ("ufw", "allow", "from", reseau, "to", "any", "port", ssh, "proto", "tcp",
                      "comment", "SSH, reseau local")):
        fait = sudo(*commande)
        if fait.returncode != 0:
            raise Stop(f"`ufw {' '.join(commande[1:])}` a échoué : {fait.stderr.strip()}")
    if f"port {ssh} " not in sudo("ufw", "show", "added").stdout + " ":
        raise Stop("la règle SSH n'apparaît pas dans `ufw show added` : activation refusée")
    ok(f"UFW : entrée refusée, sortie autorisée, SSH depuis le réseau local")
    texte = sans_bloc(lu.stdout).rstrip("\n") + "\n" + bloc(lignes)
    if sudo("tee", AFTER_RULES, entree=texte).returncode != 0:
        raise Stop(f"écriture de {AFTER_RULES} impossible")
    ok(f"bloc DOCKER-USER écrit dans {AFTER_RULES}")


def session_ssh_autorisee(reseau: ipaddress.IPv4Network) -> bool:
    """La session SSH en cours vient-elle du réseau local autorisé ?"""
    client = (os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT") or "").split()
    try:
        return bool(client) and ipaddress.ip_address(client[0]) in reseau
    except ValueError:
        return False


def activer(reseau: ipaddress.IPv4Network) -> None:
    sudo("systemctl", "stop", f"{SECOURS}.timer")
    sudo("systemctl", "reset-failed", f"{SECOURS}.service", f"{SECOURS}.timer")
    secours = sudo("systemd-run", f"--unit={SECOURS}", f"--on-active={DELAI_SECOURS}", "/usr/sbin/ufw", "disable")
    if secours.returncode != 0:
        raise Stop(f"désactivation de secours impossible à programmer : activation refusée ({secours.stderr.strip()})")
    ok(f"désactivation automatique programmée dans {DELAI_SECOURS // 60} minutes")
    deja_actif = "Status: active" in sudo("ufw", "status").stdout
    commande = ("ufw", "reload") if deja_actif else ("ufw", "--force", "enable")
    if sudo(*commande).returncode != 0:
        raise Stop(f"`{' '.join(commande)}` a échoué")
    ok("pare-feu rechargé avec les nouvelles règles" if deja_actif else "pare-feu activé")
    if session_ssh_autorisee(reseau):
        sudo("systemctl", "stop", f"{SECOURS}.timer")
        ok("ta session SSH vient du réseau local autorisé : désactivation automatique annulée")
    else:
        warn(f"session SSH hors du réseau local, ou lancement sans SSH : le pare-feu se désactivera seul dans "
             f"{DELAI_SECOURS // 60} minutes ; annuler à la main si l'accès est sûr : "
             f"sudo systemctl stop {SECOURS}.timer")


def verifier(lignes: list[str]) -> None:
    sudo("ufw", "reload")
    actuelles = sudo("iptables", "-S", "DOCKER-USER").stdout.splitlines()
    manquantes = [r for r in lignes if actuelles.count(r) != 1]
    if manquantes:
        fail(f"{len(manquantes)} règle(s) DOCKER-USER absente(s) ou en double après `ufw reload` :")
        for r in manquantes:
            print(f"          {r}")
    else:
        ok(f"les {len(lignes)} règles DOCKER-USER sont présentes une seule fois, même après `ufw reload`")
    print(f"\nRevenir en arrière : sudo ufw disable ; sudo cp {SAUVEGARDE} {AFTER_RULES} ; sudo iptables -F DOCKER-USER")


def executer() -> None:
    if not run(["sh", "-c", "command -v ufw"]).stdout.strip():
        raise Stop("ufw est introuvable : sudo apt install ufw, puis relancer")
    print("Le mot de passe sudo peut être demandé.")
    if subprocess.run(["sudo", "-v"], check=False).returncode != 0:
        raise Stop("sudo refusé : rien n'a été modifié")

    interface, reseau = interface_et_reseau()
    ssh = port_ssh()
    publies = ports_publies()
    proxy, reserves, fermes = lire_local(reseau)
    inconnus = (reserves | fermes) - set(publies)
    if inconnus:
        warn(f"pare-feu.local cite des conteneurs sans port publié, ignorés : {', '.join(sorted(inconnus))}")

    par_proxy = [p for nom, ports in publies.items() if nom in reserves for p in ports]
    en_local = [p for nom, ports in publies.items() if nom not in reserves and nom not in fermes for p in ports]
    lignes = regles(interface, str(reseau), proxy, par_proxy, en_local)

    ok(f"interface {interface}, réseau local {reseau}, SSH port {ssh} (lus sur la machine)")
    for nom, ports in publies.items():
        source = "reverse proxy seulement" if nom in reserves else "fermé" if nom in fermes else "réseau local"
        print(f"          {nom} ({', '.join(ports)}) : {source}")
    if not LOCAL.exists():
        print("          (aucun pare-feu.local : tous les ports publiés sont ouverts au réseau local, fermés au-delà)")
    if not ask_yes("Appliquer et activer le pare-feu ?", default=False):
        raise Stop("rien n'a été modifié")

    appliquer(str(reseau), ssh, lignes)
    activer(reseau)
    verifier(lignes)
