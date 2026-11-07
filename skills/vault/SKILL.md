---
name: vault
description: Déposer une note dans l'Inbox du vault de l'utilisateur (son second cerveau), ou y lancer /commit, sur sa demande.
version: 1.0.0
platforms: [linux]
---

# Le vault de l'utilisateur

## When to Use

- L'utilisateur demande de garder quelque chose dans son vault, son second cerveau, ou de le « capturer » :
  une idée, une décision, une synthèse.
- L'utilisateur demande de commiter le vault.

Jamais de ta propre initiative : seulement quand l'utilisateur le demande.

## Procedure

Le vault vit sur le serveur, sous un compte dédié. Tu le joins en SSH, et ce compte n'accepte que trois actions ;
toute autre commande est refusée.

**Déposer une note** : son contenu sur l'entrée standard, son nom en argument.

```bash
ssh -F /opt/data/home/.ssh/config vault inbox nom-de-la-note.md < /tmp/nom-de-la-note.md
```

- Nom en minuscules avec tirets, terminé par `.md` (exemple : `idee-planification-hebdo.md`).
- Le contenu commence par ce préambule, rempli :

  ```markdown
  ---
  source: Telegram, conversation avec Hermes
  date: AAAA-MM-JJ
  intention: distiller
  ---
  ```

  `intention` vaut `distiller` (à découper en notes), `garder-tel-quel` (une réflexion à garder entière) ou
  `brouillon`.
- Aucun tag, aucun lien `[[...]]` : le vault les crée lui-même au triage.
- Une note existante n'est jamais écrasée : choisir un autre nom.

**Commiter le vault** : commite les notes de l'Inbox et les pousse sur le dépôt du vault, sans autre question.

```bash
ssh -F /opt/data/home/.ssh/config vault commit
```

**La liste des actions** (ne modifie rien) :

```bash
ssh -F /opt/data/home/.ssh/config vault aide
```

## Pitfalls

- `refusé : …` : la demande ne respecte pas les règles ci-dessus ; corriger, ne jamais contourner.
- `Connection refused` ou `Permission denied (publickey)` : le lien n'est plus en place ; le dire à l'utilisateur,
  qui relance `python3 install.py --vault` sur le serveur.
- Tu ne lis pas le vault et tu ne le modifies pas autrement : ce compte ne le permet pas.

## Verification

- Après un dépôt : la réponse est `déposé : 00 - Inbox/<nom>`.
- Après un commit : la réponse donne le message du commit et le résultat du push, ou « rien à commiter ». Un push
  refusé est à rapporter tel quel à l'utilisateur : le commit reste fait sur le serveur.
