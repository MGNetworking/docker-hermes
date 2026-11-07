---
name: vault
description: Le vault de l'utilisateur (son second cerveau) - y déposer une note, ou transmettre toute autre demande (tri, commit, recherche…) à Claude Code, qui travaille dans le vault.
version: 2.0.0
platforms: [linux]
---

# Le vault de l'utilisateur

## When to Use

- L'utilisateur demande de garder quelque chose dans son vault, son second cerveau, ou de le « capturer » :
  une idée, une décision, une synthèse.
- L'utilisateur demande quoi que ce soit d'autre sur son vault : trier l'Inbox, commiter, pousser, chercher une
  note, la ranger…

Jamais de ta propre initiative : seulement quand l'utilisateur le demande.

## Procedure

Le vault vit sur le serveur, sous un compte dédié, que tu joins en SSH. **Ce n'est pas toi qui travailles dans le
vault : c'est Claude Code**, qui y connaît les règles et les commandes (`/triage`, `/commit`…). Toi, tu transmets la
demande de l'utilisateur, et tu lui relaies la réponse.

**Toute demande sur le vault** : transmettre le texte de l'utilisateur tel quel, sans le reformuler, sur l'entrée
standard.

```bash
ssh -F /opt/data/home/.ssh/config vault claude < /tmp/demande.txt
```

**Quand Claude Code pose une question** (sa réponse se termine par des choix) : la relayer telle quelle à
l'utilisateur, puis transmettre sa réponse dans la même conversation :

```bash
ssh -F /opt/data/home/.ssh/config vault suite < /tmp/reponse.txt
```

`claude` ouvre une nouvelle conversation ; `suite` continue la dernière. Ne jamais mélanger deux sujets : une
nouvelle demande, c'est `claude`.

**Déposer une note**, sans Claude Code (plus rapide, gratuit) : son contenu sur l'entrée standard, son nom en
argument.

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

  `intention` vaut `distiller` (à découper en notes), `garder-tel-quel` (une réflexion à garder entière),
  `brouillon`, ou `à-évaluer` (ci-dessous).
- **Un résumé à évaluer** : quand l'utilisateur demande de résumer une lecture (article, vidéo, documentation) pour
  décider plus tard s'il la garde. Le résumé tient en quelques lignes et sépare deux sections : « Ce que l'auteur
  affirme » et « Ce qui est établi » (vérifiable, ou reconnu largement). `intention: à-évaluer`, et `source` porte
  l'URL telle quelle. Au tri, l'utilisateur décidera de l'absorber ou de la jeter.
- Aucun tag, aucun lien `[[...]]` : le vault les crée lui-même au triage.
- Une note existante n'est jamais écrasée : choisir un autre nom.

**La liste des actions** (ne modifie rien) :

```bash
ssh -F /opt/data/home/.ssh/config vault aide
```

## Pitfalls

- Ne jamais répondre toi-même à une question de Claude Code : c'est l'utilisateur qui décide.
- Chaque `claude` ou `suite` appelle un modèle payant : un appel par demande ou par réponse de l'utilisateur, pas
  plus.
- `refusé : …` : la demande ne respecte pas les règles ci-dessus ; corriger, ne jamais contourner.
- `Connection refused` ou `Permission denied (publickey)` : le lien n'est plus en place ; le dire à l'utilisateur,
  qui relance `python3 install.py --vault` sur le serveur.
- Tu ne lis pas le vault et tu ne le modifies pas autrement : ce compte ne le permet pas.

## Verification

- Après un dépôt : la réponse est `déposé : 00 - Inbox/<nom>`.
- Après `claude` ou `suite` : la réponse de Claude Code, à relayer à l'utilisateur.
