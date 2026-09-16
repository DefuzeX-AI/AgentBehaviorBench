# AgentBehaviorBench (ABB)

> Prérequis du navigateur : Node.js 20.19+ (20.x) ou 22.12+, avec npm. Dans `web/`, exécutez `npm ci` puis `npm run build` avant `agentbench view`. Les exécutions `--no-view` ne nécessitent pas cette compilation. Installation, clés et limites à jour : [guide principal (anglais)](../../README.md).

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
> Engine (en cours d'exécution). KUMA est installé automatiquement depuis PyPI
> lors de la construction du conteneur d'évaluation.
> Le Company Research Agent prêt à l'emploi requiert `KUMA_API_KEY` (ou
> `DEFUZEX_API_KEY`), `OPENROUTER_API_KEY`, `OPENROUTER_MODEL` et
> `TAVILY_API_KEY`.

AgentBehaviorBench exécute des agents IA enregistrés dans des environnements
isolés, collecte les preuves d'exécution et évalue le résultat via un SDK
sélectionnable. Le SDK par défaut est l'adaptateur KUMA intégré. Les résultats
sont enregistrés localement et consultables dans le visualiseur ABB.

![Architecture d'exécution AgentBehaviorBench](../figures/framework.png)

## Démarrage rapide

À la racine du dépôt, créez un environnement virtuel et installez ABB :

```bash
python3 -m venv .venv
source .venv/bin/activate              # Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e "."
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

Démarrez Docker, puis exécutez chaque agent dont le registre contient
`enabled = true` et dont le statut est `ready` :

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
| Docker Desktop / Docker Engine | L'agent intégré prêt à l'emploi s'exécute dans Docker. Docker doit être démarré avant `run`, `evaluate`, `certify` ou `observe`. |
| `KUMA_API_KEY` ou `DEFUZEX_API_KEY` | Accès Case et Judge du SDK KUMA par défaut. |
| `OPENROUTER_API_KEY` | Le trafic modèle des agents Docker est transmis à OpenRouter par l'intercepteur ABB. |
| `OPENROUTER_MODEL` | Modèle utilisé pour l'exécution. |
| `TAVILY_API_KEY` | Accès à la recherche web pour le Company Research Agent intégré. |

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
version installée.

| Commande | Usage |
| --- | --- |
| `agentbench run` | Évalue tous les agents activés et `ready`; commande par défaut. |
| `agentbench evaluate company-research-agent --cases 1` | Évalue un agent sur un nombre choisi de Cases indépendants. |
| `agentbench observe company-research-agent` | Exécute un agent avec une entrée native et enregistre les traces, sans Case ni Judge. |
| `agentbench certify react-agent` | Certifie un agent `adapting` et le promeut en `ready` en cas de succès. |
| `agentbench view results/benchmark.json` | Rouvre un résultat dans le visualiseur local. |
| `agentbench sdk list` | Liste les SDK d'évaluation intégrés et installés. |
| `agentbench clean --dry-run` | Affiche l'historique local qui serait déplacé vers une archive récupérable. |

Options `run` fréquentes :

```bash
agentbench run --model openai/gpt-4.1-mini
agentbench run --sdk kuma --sdk-options sdk-options.json
```

La référence complète est en anglais : [CLI reference](../../README.md#cli-and-repository-layout). Pour
ajouter un agent, consultez le [guide d'intégration](How%20To%20Add%20Agent.fr.md).

## Organisation du dépôt

```text
resources/registry.toml
        -> CLI selection
        -> SuiteRunner / evaluation SDK
        -> Agent adapter and runtime
        -> result snapshot and local viewer
```

- `resources/registry.toml` déclare les agents, leur statut et leur runtime.
- `resources/agents/` contient chaque unité d'agent et sa configuration ABB.
- `agentbench/cli/` fournit les commandes du terminal.
- `agentbench/harness/` gère l'exécution, les résultats et le registre.
- `agentbench/runtime/` exécute les agents localement ou dans Docker.
- `agentbench/sdk/plugin/` contient les adaptateurs SDK intégrés et la découverte de plugins.

## Développement

```bash
python -m pytest
```

Consultez [AGENTS.md](../../AGENTS.md) et [docs/AGENTS.md](../../AGENTS.md) pour
les conventions du dépôt.

## Licence

MIT. Voir [LICENSE](../../LICENSE).
