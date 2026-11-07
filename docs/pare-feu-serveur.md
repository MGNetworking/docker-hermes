# Le pare-feu du serveur

> Procédure à appliquer **une fois**, à la main, sur le serveur où tourne Hermes. Elle protège **tout le serveur**,
> pas seulement Hermes : elle vit ici parce que Hermes est le premier projet installé sur la machine.
>
> **Aucune valeur propre au réseau** (adresse, plage, interface, port) n'est écrite dans ce dépôt public. Elles sont
> données dans la session, au moment d'appliquer la procédure (étape 0), et n'existent que sur le serveur.

## Ce que le pare-feu autorise

- **SSH** : depuis le réseau local seulement.
- **Les services publiés derrière le reverse proxy** : depuis le reverse proxy seulement.
- **Les services consultés en direct sur le réseau local**, dont Hermes pendant les essais : depuis le réseau local.
- **Tout le reste, en entrée** : refusé.
- **En sortie** : tout autorisé (Hermes joint sa messagerie et son fournisseur de modèle, Docker télécharge ses images).

## Pourquoi deux niveaux

- **UFW** protège les ports **du serveur lui-même** : ici, SSH.
- **Docker contourne UFW** : un port publié par un conteneur reste ouvert même si UFW le ferme, parce que Docker pose
  ses propres règles avant celles d'UFW. Ces ports se filtrent dans la chaîne `DOCKER-USER`, prévue par Docker pour
  ça. Les règles sont écrites dans `/etc/ufw/after.rules`, pour qu'UFW les recharge à chaque démarrage. Elles
  reconnaissent les ports **publiés sur le serveur**, grâce à `--ctorigdstport`, sans dépendre des ports internes des
  conteneurs.

## Avant de commencer

- Être **sur le réseau local**.
- Ouvrir **deux sessions SSH** sur le serveur : la première pour les commandes, la seconde pour vérifier que SSH
  répond encore après l'activation.

## 0. Les valeurs, dans la session

Dans la première session, définir les valeurs du réseau. Elles ne vivent que dans cette session ; ne jamais les
écrire dans un fichier du dépôt.

```bash
RESEAU_LOCAL='<plage du réseau local, ex. forme a.b.c.0/24>'
PROXY='<adresse du reverse proxy>'
INTERFACE='<interface réseau du serveur, voir : ip -br addr>'
PORTS_PROXY='<ports publiés joints par le reverse proxy, séparés par des espaces ; une plage s'écrit début:fin>'
PORTS_LOCAL='<ports publiés consultés en direct sur le réseau local, séparés par des espaces>'
```

Les ports publiés par les conteneurs se lisent avec `docker ps` (colonne `PORTS`, la partie avant `->`).

## 1. L'état de départ

```bash
sudo ufw status verbose
sudo iptables -S DOCKER-USER
```

Attendu : `Status: inactive`, et une chaîne `DOCKER-USER` vide (`-N DOCKER-USER`).

## 2. Les règles UFW (rien n'est encore actif)

```bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow from "$RESEAU_LOCAL" to any port 22 proto tcp comment 'SSH, reseau local'
sudo ufw show added
```

Vérifier que `ufw show added` affiche bien la règle du port SSH.

## 3. Les règles des ports Docker

Sauvegarder `after.rules` :

```bash
sudo cp /etc/ufw/after.rules /etc/ufw/after.rules.avant-docker-user
```

Composer le bloc `DOCKER-USER` à partir des valeurs de l'étape 0, et le relire avant de l'ajouter :

```bash
{
  printf '\n# BEGIN DOCKER-USER (hermes/docs/pare-feu-serveur.md)\n*filter\n:DOCKER-USER - [0:0]\n'
  printf -- '-A DOCKER-USER -m conntrack --ctstate RELATED,ESTABLISHED -j RETURN\n'
  printf -- '-A DOCKER-USER ! -i %s -j RETURN\n' "$INTERFACE"
  for p in $PORTS_PROXY; do
    printf -- '-A DOCKER-USER -s %s -p tcp -m conntrack --ctorigdstport %s -j RETURN\n' "$PROXY" "$p"
  done
  for p in $PORTS_LOCAL; do
    printf -- '-A DOCKER-USER -s %s -p tcp -m conntrack --ctorigdstport %s -j RETURN\n' "$RESEAU_LOCAL" "$p"
  done
  printf -- '-A DOCKER-USER -i %s -j DROP\nCOMMIT\n# END DOCKER-USER\n' "$INTERFACE"
} > /tmp/docker-user.rules && cat /tmp/docker-user.rules
```

Si le bloc affiché est correct :

```bash
sudo tee -a /etc/ufw/after.rules < /tmp/docker-user.rules > /dev/null && rm /tmp/docker-user.rules
```

Ligne par ligne : les réponses des connexions déjà ouvertes passent ; le trafic qui n'arrive pas par l'interface
réseau (par exemple entre conteneurs) passe ; chaque port publié n'est accepté que depuis sa source ; tout le reste
arrivant par le réseau est rejeté.

## 4. L'activation prudente

Programmer d'abord une **désactivation automatique dans 3 minutes**, au cas où SSH serait coupé :

```bash
sudo systemd-run --unit=pare-feu-secours --on-active=180 /usr/sbin/ufw disable
```

Activer :

```bash
sudo ufw --force enable
```

**Dans la seconde session SSH**, ou en ouvrant une nouvelle connexion depuis le PC : si elle répond, annuler la
désactivation automatique :

```bash
sudo systemctl stop pare-feu-secours.timer
```

Si plus rien ne répond : ne rien toucher, attendre 3 minutes, UFW se désactive seul et l'accès revient.

## 5. Les vérifications

Sur le serveur :

```bash
sudo ufw status verbose
sudo iptables -S DOCKER-USER
sudo ufw reload && sudo iptables -S DOCKER-USER
```

La chaîne `DOCKER-USER` doit montrer ses règles **une seule fois**, y compris après `ufw reload`.

Depuis le PC :

- un service de `PORTS_LOCAL` (par exemple le Dashboard de Hermes) s'ouvre en direct ;
- un service de `PORTS_PROXY`, appelé **en direct** par l'adresse du serveur, ne répond **plus** (délai dépassé) ;
- le même service, appelé **par son nom de domaine** (donc par le reverse proxy), répond toujours.

Enfin, redémarrer le serveur (`sudo reboot`) et refaire ces vérifications : les règles doivent tenir.

## 6. Plus tard : Hermes réservé au reverse proxy

Quand Hermes sera joint par un nom de domaine, déplacer ses ports de la source « réseau local » vers la source
« reverse proxy » dans le bloc de `/etc/ufw/after.rules`, puis `sudo ufw reload`.

## Revenir en arrière

```bash
sudo ufw disable
sudo cp /etc/ufw/after.rules.avant-docker-user /etc/ufw/after.rules
sudo iptables -F DOCKER-USER
```
