# Comprendre `registry.toml`

[English](../Registry.md) | [中文](Registry.zh-CN.md) | Français | [日本語](Registry.ja.md) | [한국어](Registry.ko.md)

[Retour au README](README.fr.md) · [Démarrer ABB — anglais](../Guide.md)

Le [registre des Agents](../../resources/registry.toml) décrit les Agents cibles
disponibles, leurs répertoires d’intégration et leurs budgets d’évaluation par défaut.
`agentbench run` sélectionne les entrées ayant à la fois `enabled = true` et
`status = "ready"`.

## Lire une entrée

Le fichier commence par la version du format. Chaque bloc `[[agents]]` inscrit un Agent :

```toml
schema_version = "defuzex-bench.registry.v1"

[[agents]]
agent_id = "folder-mover-agent"
path = "resources/agents/01-folder-mover-agent"
enabled = false
status = "ready"
framework = "langgraph"
source = "C:\\Song_startup\\benchmark\\04-folder-mover-agent\\folder-mover-agent"
case = 1
step = 3
```

Cet Agent LangGraph dispose par défaut d’un Case indépendant comportant au maximum
trois étapes de dialogue. Il est marqué `ready`, mais désactivé : `run` l’exclut.
Le chemin `source` illustre l’emplacement d’importation initial sur une machine ;
les utilisateurs n’ont pas à créer ce même répertoire.

| Champ | Signification |
| --- | --- |
| `schema_version` | Identifiant du format du fichier. Conserver `"defuzex-bench.registry.v1"`, une seule fois avant les blocs d’Agents. |
| `[[agents]]` | Syntaxe TOML de tableau de tables : chaque bloc inscrit un Agent distinct. |
| `agent_id` | Identifiant unique utilisé dans les commandes CLI. Doit correspondre à celui du fichier `agent.toml` de l’Agent. |
| `path` | Répertoire local d’intégration, relatif à la racine du dépôt lorsque le registre est à son emplacement standard. Désigne le répertoire externe contenant `agent.toml` et `requirement.md`, plutôt que le sous-répertoire source `agent/`. Doit rester dans le dépôt. |
| `enabled` | Autorise la sélection de l’Agent. `false` l’exclut de `run` et de la sélection par `evaluate`. Utiliser un booléen TOML ; valeur par défaut : `true`. |
| `status` | État d’intégration. `adapting` indique une intégration en attente de certification ; `ready` autorise la sélection par `run` si l’Agent est activé. Valeur par défaut : `unknown`, exclue de `run`. |
| `framework` | Étiquette du framework, par exemple `langgraph` ou `acp`, cohérente avec le manifeste et l’intégration réelle. L’Adapter d’exécution et le démarrage sont définis dans `agent.toml`. |
| `source` | Origine du code : URL de dépôt ou répertoire d’importation local. La modifier ne remplace pas le code importé et ne configure pas le démarrage. Valeur par défaut : chaîne vide. |
| `case` | Nombre de Cases indépendants pour cet Agent. Entier strictement positif ; valeur par défaut : `1`. |
| `step` | Limite SDK du nombre d’étapes de dialogue par Case. Entier strictement positif si présent ; sinon, le SDK applique sa valeur par défaut. Un Case peut comporter moins d’étapes. |

`agent_id`, `path` et `framework` sont des chaînes non vides obligatoires. Dans une
chaîne TOML entre guillemets doubles, écrire les antislashs Windows sous la forme `\\`.

## Distinguer `case` et `step`

- `case = 1`, `step = 3` : un Case indépendant, avec au maximum trois entrées ordonnées.
- `case = 5`, `step = 3` : cinq Cases indépendants, chacun avec au maximum trois entrées.
- Une étape de dialogue soumet une entrée à l’Agent cible, qui peut effectuer plusieurs
  appels de modèle et d’outils. `step` ne limite donc ni les appels d’outils ni les
  itérations de raisonnement internes. Ces champs ne règlent pas la concurrence.

Certains Agents ne prennent pas en charge plusieurs étapes de dialogue ; nous
recommandons donc de conserver la valeur `step` par défaut définie par le benchmark
pour chaque Agent.

Le SDK sélectionné applique le budget lors de la génération et de l’exécution.
Une option SDK explicite `max_steps` prévaut sur `step`. Pour `evaluate`, `--cases`
remplace `case` et `--max-steps` remplace le budget d’étapes pour cette exécution,
sans modifier le registre :

```bash
agentbench evaluate react-agent --cases 2 --max-steps 3 --no-view
```

## Sélectionner les Agents et ajuster les valeurs par défaut

Pour inclure l’Agent de l’exemple dans `run`, définir `enabled = true`. Pour une
nouvelle intégration `adapting`, terminer la [configuration](How%20To%20Add%20Agent.fr.md)
et certifier l’Agent lorsqu’il est activé :

```bash
agentbench certify folder-mover-agent --no-view
```

Une certification réussie fait passer l’Agent à `ready`. Ce statut atteste de
l’intégration, sans garantir l’absence de défauts comportementaux selon le Judge.
Le modifier manuellement n’effectue aucune certification. Contrairement à `run`,
`evaluate` sélectionne un Agent activé sans filtrer sur `ready`.

```bash
agentbench observe --list
agentbench run --no-view
```

Modifier `case` et `step` ajuste les budgets des futures exécutions. Les Cases et
résultats enregistrés conservent leur configuration. `run` valide toutes les entrées
avant de sélectionner les Agents activés et prêts : des fichiers d’intégration
manquants, même pour un Agent désactivé, peuvent empêcher le chargement du registre.
Conserver des chemins valides, des identifiants uniques et les fichiers requis.
Voir aussi les [Agents intégrés](Agents.fr.md).
