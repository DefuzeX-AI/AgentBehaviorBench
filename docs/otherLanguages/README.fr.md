# AgentBehaviorBench (ABB)

<p align="center">
  <img alt="AgentBehaviorBench — agents lamas qui évaluent des flux" src="../figures/title.png" width="720" style="border-radius: 24px;">
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  Français |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文简体</a> |
  <a href="README.zh-TW.md">中文繁體</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10+" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="Licence MIT" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

> **Avant d'exécuter ABB :** installez Python 3.10+, Docker Desktop ou Docker
> Engine (en cours d'exécution), et Node.js 20.19+ ou 22.12+ pour construire le
> visualiseur de résultats. KUMA est installé automatiquement depuis PyPI lors de la
> construction du conteneur d'évaluation. Les deux agents intégrés requièrent
> `KUMA_API_KEY` (ou `DEFUZEX_API_KEY`), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` et
> `TAVILY_API_KEY`.

AgentBehaviorBench exécute des agents IA enregistrés dans des environnements
isolés, collecte les preuves d'exécution et évalue le résultat via un SDK
sélectionnable. Le SDK par défaut est l'adaptateur KUMA intégré. Les résultats
sont enregistrés localement et consultables dans le visualiseur ABB.

![Architecture d'exécution AgentBehaviorBench](../figures/framework.png)

En cas d'erreur au premier lancement, consultez d'abord le
[dépannage](#dépannage) ci-dessous.

## Démarrage rapide

À la racine du dépôt, créez un environnement virtuel et installez ABB :

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
```

Le visualiseur de résultats se construit depuis `web/` et n'est pas versionné.
Construisez-le une fois avant d'ouvrir des résultats ; `run`, `evaluate` et
`certify` le lancent après une exécution, et `agentbench view` rouvre un résultat
enregistré :

```bash
(cd web && npm ci && npm run build)   # Windows PowerShell: cd web; npm ci; npm run build; cd ..
```

Créez le fichier d'environnement local et renseignez les identifiants :

```bash
cp .env.example .env                   # Windows PowerShell: Copy-Item .env.example .env
```

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
TAVILY_API_KEY=
```

`KUMA_API_KEY` est le nom documenté par le SDK KUMA ; ABB accepte aussi l'alias
`DEFUZEX_API_KEY`, utilisé seulement si `KUMA_API_KEY` est vide. `OPENROUTER_MODEL`
est obligatoire et n'a pas de valeur par défaut : la valeur ci-dessus n'est qu'un
exemple, choisissez un modèle accessible à votre compte.

Démarrez Docker (`docker info` doit réussir). Le registre versionné active deux
agents, tous deux `ready` : `react-agent` et `company-research-agent`. Évaluez
d'abord un Case ; cela appelle les services Case et Judge de KUMA, facturés sur
votre clé :

```bash
agentbench evaluate react-agent --cases 1 --max-steps 1
```

Exécutez ensuite chaque agent dont le registre contient `enabled = true` et dont
le statut est `ready` :

```bash
agentbench run
```

ABB demande une confirmation, enregistre un instantané dans `results/` et lance
le visualiseur local. Pour une exécution sans interface :

```bash
agentbench run --yes --no-view --output results/benchmark.json
```

## Prérequis et variables d'environnement

| Prérequis | Utilité |
| --- | --- |
| Python 3.10 ou ultérieur | CLI et harness ABB. |
| Docker Desktop / Docker Engine | Les agents intégrés s'exécutent dans Docker. Docker doit être démarré avant `run`, `evaluate`, `certify` ou `observe`. |
| Node.js 20.19+ ou 22.12+ avec npm | Construit une fois le visualiseur `web/`. Inutile pour les exécutions sans interface (`--no-view`). |
| `KUMA_API_KEY` ou `DEFUZEX_API_KEY` | Accès Case et Judge du SDK KUMA par défaut. `KUMA_API_KEY` l'emporte si les deux sont définies. |
| `OPENROUTER_API_KEY` | Le trafic modèle des agents Docker est transmis à OpenRouter par l'intercepteur ABB. |
| `OPENROUTER_MODEL` | Nom de modèle obligatoire. La valeur de `.env.example` est un exemple, pas une valeur par défaut ; choisissez un modèle accessible à votre compte. |
| `TAVILY_API_KEY` | Recherche web des deux agents intégrés, ReAct et Company Research. |

`.env` est ignoré par Git. Les variables déjà exportées par le shell remplacent
les valeurs de `.env`; `--env-file PATH` choisit un autre fichier dotenv; et
`--model MODEL` remplace le modèle pour une commande.

Variables OpenRouter facultatives :

```dotenv
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_HTTP_REFERER=https://example.com
OPENROUTER_APP_TITLE=AgentBehaviorBench
```

## CLI

Exécutez `agentbench --help` ou `agentbench <command> --help` pour l'aide de la
version installée ; c'est la référence complète des options.

| Commande | Usage |
| --- | --- |
| `agentbench run` | Évalue tous les agents activés et `ready`; commande par défaut. |
| `agentbench evaluate company-research-agent --cases 1` | Évalue un agent sur un nombre choisi de Cases indépendants. |
| `agentbench observe company-research-agent` | Exécute un agent avec une entrée native et enregistre les traces, sans Case ni Judge. |
| `agentbench certify NEW-AGENT` | Certifie un agent `adapting` et le promeut en `ready` en cas de succès. |
| `agentbench view RESULT.json` | Rouvre dans le visualiseur local le résultat dont le chemin horodaté suit `Result saved:` à la fin d'une exécution (construisez `web/` d'abord ; voir Démarrage rapide). |
| `agentbench sdk list` | Liste les répertoires d'adaptateurs SDK sans importer leurs implémentations. |
| `agentbench clean --dry-run` | Affiche les entrées non référencées de `results/` que `clean` déplacerait dans `cache/history-trash/`. Rien n'est supprimé. |

Options `run` fréquentes :

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

Pour ajouter un agent (`agent add`), consultez la
[section CLI du README anglais](../../README.md#cli) (en anglais) et le
[guide d'intégration](../How%20To%20Add%20Agent.md) (en anglais).

## Dépannage

Voici les échecs du premier lancement, tels que `evaluate`, `run` ou `certify` les
affichent. Sauf la ligne sur le nom de modèle, tous s'arrêtent avant toute requête
KUMA et ne coûtent rien.

| Sortie | Cause | Solution |
| --- | --- | --- |
| `DockerUnavailableError: Docker daemon is unavailable: failed to connect to the docker API …` | Docker n'est pas démarré, ou `DOCKER_HOST` ne désigne aucun démon. | Démarrez Docker Desktop ou le service Docker jusqu'à ce que `docker info` réussisse. |
| `[Configuration error] KUMA_API_KEY or DEFUZEX_API_KEY is required` | Aucun identifiant KUMA dans l'environnement ni dans `.env`. | Définissez `KUMA_API_KEY` dans `.env`. |
| `ConfigurationError: KUMA API keys must begin with 'dfx_'` | La variable contient autre chose qu'une clé KUMA, par exemple une clé OpenRouter. | Utilisez la clé `dfx_` émise pour KUMA. |
| `AuthenticationError: Invalid API key.` après `GET defuzex.ai/… \| HTTP 401` | La clé KUMA est erronée, révoquée ou destinée à un autre Backend. | Remplacez la clé ; vérifiez `KUMA_BASE_URL` si vous l'avez défini. |
| `InterceptionConfigurationError: OpenRouter model is required; pass --model or set OPENROUTER_MODEL` | `OPENROUTER_MODEL` n'est pas défini ; ABB n'a pas de modèle par défaut. | Définissez `OPENROUTER_MODEL` dans `.env`, ou passez `--model`. |
| `MissingSecretError: Required secret is not configured in the environment: OPENROUTER_API_KEY` (ou `TAVILY_API_KEY`) | Un identifiant requis par l'amont modèle ou par le `agent.toml` de l'agent manque. | Ajoutez la variable indiquée à `.env` ou exportez-la. |
| `LLM call 01 \| openrouter \| FAILED`, puis `related network: upstream_error POST …` citant le fournisseur | L'amont modèle a refusé l'appel, par exemple un nom de modèle inconnu ou une clé sans accès. Le Case était déjà généré et peut encore être jugé et facturé. | Utilisez un nom de modèle que votre fournisseur propose pour votre clé. |
| `Trace UI not built or incomplete. Run: cd …/web && npm ci && npm run build` | Le visualiseur n'a pas été construit dans ce dépôt. | Exécutez la commande affichée avec Node.js 20.19+ ou 22.12+. |

`agentbench clean` ne supprime rien : il liste les entrées de premier niveau non
référencées de `results/`, demande confirmation, puis les déplace dans
`cache/history-trash/<horodatage>/`. Les Suites enregistrées et les artefacts
qu'elles référencent restent en place. Pour annuler, arrêtez les exécutions et les
visualiseurs, puis replacez les entrées archivées dans `results/`.

## Organisation du dépôt

```text
AgentBehaviorBench/
├── resources/registry.toml
├── resources/agents/
├── agentbench/cli/
├── agentbench/harness/
├── agentbench/runtime/
├── agentbench/sdk/plugin/kuma/
├── web/
└── results/
```

- `resources/registry.toml` déclare les agents, leur statut et leur runtime.
- `resources/agents/` contient chaque unité d'agent et sa configuration ABB.
- `agentbench/cli/` fournit les commandes du terminal.
- `agentbench/harness/` gère l'exécution, les résultats et le registre.
- `agentbench/runtime/` exécute les agents localement ou dans Docker.
- `agentbench/sdk/plugin/` contient les adaptateurs SDK intégrés et leur découverte par répertoire.
- `web/` contient les sources du visualiseur ; `npm run build` produit le
  `web/dist` servi par la CLI.

Le flux d'exécution est : `resources/registry.toml` → sélection CLI →
SuiteRunner / SDK d'évaluation → adaptateur et runtime de l'agent → instantané de
résultat et visualiseur local (voir le schéma d'architecture ci-dessus).

## Développement

```bash
python -m pytest
```

Consultez [AGENTS.md](../../AGENTS.md) (en anglais) pour les conventions du dépôt.

## Licence

MIT. Voir [LICENSE](../../LICENSE).
