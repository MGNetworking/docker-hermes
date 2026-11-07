"""Mettre en place le pare-feu du serveur (UFW et les ports Docker), avec une désactivation automatique de secours.

Le pare-feu protège tout le serveur, pas seulement Hermes. Aucune valeur du réseau (plage, adresse, interface, port)
n'est écrite dans le dépôt : elles sont demandées ici, appliquées sur la machine, et nulle part ailleurs.

- UFW : entrée refusée par défaut, sortie autorisée, SSH accepté depuis le réseau local.
- Docker contourne UFW : les ports publiés par les conteneurs se filtrent dans la chaîne DOCKER-USER, écrite dans
  /etc/ufw/after.rules pour être rechargée à chaque démarrage. Chaque port publié est accepté depuis le reverse proxy,
  depuis le réseau local, ou nulle part (choix demandé conteneur par conteneur).
- Avant l'activation, une désactivation automatique est programmée : si SSH ne répond plus, l'accès revient seul.
"""

from __future__ import annotations

import ipaddress
import re
import subprocess

from installation.commun import Stop, ask, ask_yes, fail, ok, run, warn

AFTER_RULES = "/etc/ufw/after.rules"
SAUVEGARDE = "/etc/ufw/after.rules.avant-docker-user"
DEBUT = "# BEGIN DOCKER-USER (hermes/installation/pare_feu.py)"
FIN = "# END DOCKER-USER"
SECOURS = "pare-feu-secours"
DELAI_SECOURS = 180  # secondes


def sudo(*args: str, entree: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["sudo", *args], input=entree, capture_output=True, text=True, check=False)


def lire_after_rules() -> str:
    lu = sudo("cat", AFTER_RULES)
    if lu.returncode != 0:
        raise Stop(f"lecture de {AFTER_RULES} impossible : {lu.stderr.strip()}")
    return lu.stdout


def sans_bloc(texte: str) -> str:
    """after.rules sans un éventuel bloc DOCKER-USER posé par ce script (pour le remplacer, jamais le doubler)."""
    return re.sub(r"\n*# BEGIN DOCKER-USER[^\n]*\n.*?# END DOCKER-USER\n?", "\n", texte, flags=re.S)


# ── Les valeurs, demandées et jamais écrites dans le dépôt ───────────────────────────────────────────


def interface_par_defaut() -> str:
    route = run(["ip", "route", "show", "default"]).stdout.split()
    return route[route.index("dev") + 1] if "dev" in route else ""


def demander_reseau(question: str, defaut: str = "") -> ipaddress.IPv4Network:
    while True:
        try:
            return ipaddress.ip_network(ask(question, defaut), strict=False)
        except ValueError:
            print("  Forme attendue : a.b.c.0/24")


def demander_adresse(question: str, reseau: ipaddress.IPv4Network) -> ipaddress.IPv4Address:
    while True:
        try:
            adresse = ipaddress.ip_address(ask(question))
        except ValueError:
            print("  Forme attendue : a.b.c.d")
            continue
        if adresse in reseau:
            return adresse
        print(f"  Cette adresse n'est pas dans le réseau local ({reseau}).")


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


def demander_sources(publies: dict[str, list[str]]) -> tuple[list[str], list[str]]:
    print("\nPour chaque conteneur, d'où ses ports publiés doivent être joignables :")
    print("  p = le reverse proxy seulement   l = le réseau local   f = nulle part (fermé)")
    par_proxy: list[str] = []
    en_local: list[str] = []
    for nom, ports in publies.items():
        while True:
            choix = ask(f"{nom} ({', '.join(ports)})", "l").lower()
            if choix in ("p", "l", "f"):
                break
            print("  Répondre p, l ou f.")
        (par_proxy if choix == "p" else en_local if choix == "l" else []).extend(ports)
    return par_proxy, en_local


def regles(interface: str, reseau: str, proxy: str, par_proxy: list[str], en_local: list[str]) -> list[str]:
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


# ── L'application ─────────────────────────────────────────────────────────────────────────────────────


def port_ssh() -> str:
    lu = sudo("sshd", "-T")
    for ligne in lu.stdout.splitlines():
        if ligne.startswith("port "):
            return ligne.split()[1]
    raise Stop("port d'écoute de sshd introuvable (`sshd -T`) : rien n'a été modifié")


def appliquer(reseau: str, ssh: str, texte_after: str) -> None:
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
    ajoutees = sudo("ufw", "show", "added").stdout
    if f"port {ssh} " not in ajoutees + " " and f" {ssh}/tcp" not in ajoutees:
        raise Stop("la règle SSH n'apparaît pas dans `ufw show added` : activation refusée")
    ok(f"UFW : entrée refusée, sortie autorisée, SSH (port {ssh}) depuis le réseau local")
    if sudo("tee", AFTER_RULES, entree=texte_after).returncode != 0:
        raise Stop(f"écriture de {AFTER_RULES} impossible")
    ok(f"bloc DOCKER-USER écrit dans {AFTER_RULES}")


def activer() -> None:
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
    print("\nOuvre maintenant une NOUVELLE connexion SSH vers le serveur, depuis ton PC.")
    if ask_yes("La nouvelle connexion répond-elle ?", default=False):
        sudo("systemctl", "stop", f"{SECOURS}.timer")
        ok("désactivation automatique annulée : le pare-feu reste actif")
    else:
        warn(f"rien n'est annulé : le pare-feu se désactivera seul dans moins de {DELAI_SECOURS // 60} minutes")
        raise Stop("SSH ne répond pas avec le pare-feu : vérifier le réseau local et le port SSH, puis relancer")


def verifier(lignes: list[str]) -> None:
    sudo("ufw", "reload")
    actuelles = sudo("iptables", "-S", "DOCKER-USER").stdout.splitlines()
    manquantes = [r for r in lignes if actuelles.count(r) != 1]
    if manquantes:
        fail(f"{len(manquantes)} règle(s) DOCKER-USER absente(s) ou en double après `ufw reload`")
        for r in manquantes:
            print(f"          {r}")
    else:
        ok(f"les {len(lignes)} règles DOCKER-USER sont présentes une seule fois, même après `ufw reload`")
    print("\nÀ vérifier depuis ton PC : un service ouvert au réseau local répond en direct ; un service réservé au")
    print("reverse proxy ne répond plus en direct, mais répond par son nom de domaine. Puis `sudo reboot` et recommencer.")
    print(f"Revenir en arrière : sudo ufw disable ; sudo cp {SAUVEGARDE} {AFTER_RULES} ; sudo iptables -F DOCKER-USER")


def executer() -> None:
    if not run(["sh", "-c", "command -v ufw"]).stdout.strip():
        raise Stop("ufw est introuvable : sudo apt install ufw, puis relancer")
    print("Le mot de passe sudo peut être demandé.")
    if subprocess.run(["sudo", "-v"], check=False).returncode != 0:
        raise Stop("sudo refusé : rien n'a été modifié")

    texte = lire_after_rules()
    if DEBUT.split(" (")[0] in texte:
        warn("un bloc DOCKER-USER existe déjà dans after.rules : il sera remplacé, pas doublé")

    print("\nLes valeurs du réseau : elles ne sont écrites que sur cette machine.")
    reseau = demander_reseau("Plage du réseau local (a.b.c.0/24)")
    proxy = demander_adresse("Adresse du reverse proxy", reseau)
    while True:
        interface = ask("Interface réseau du serveur", interface_par_defaut())
        if re.fullmatch(r"[A-Za-z0-9._-]{1,15}", interface):
            break
        print("  Un nom d'interface (voir : ip -br addr).")
    ssh = port_ssh()
    par_proxy, en_local = demander_sources(ports_publies())

    lignes = regles(interface, str(reseau), str(proxy), par_proxy, en_local)
    print(f"\nUFW : entrée refusée sauf SSH (port {ssh}) depuis {reseau} ; sortie autorisée.")
    print("Règles DOCKER-USER :")
    for r in lignes:
        print(f"  {r}")
    if not ask_yes("Appliquer ces règles et activer le pare-feu ?", default=False):
        raise Stop("rien n'a été modifié")

    appliquer(str(reseau), ssh, sans_bloc(texte).rstrip("\n") + "\n" + bloc(lignes))
    activer()
    verifier(lignes)
