# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench (ABB)"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  <a href="../README.md">English</a> |
  Français |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文简体</a> |
  <a href="README.zh-TW.md">中文繁體</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="License" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Package" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## Actualités

- AgentBehaviorBench (ABB) exécute maintenant les Agents LangGraph enregistrés au moyen du protocole de poignée de main `get_input()` / `submit()` du SDK DefuzeX.

## Vue d'ensemble

AgentBehaviorBench (ABB) est un benchmark destiné à évaluer des Agents IA sur des tâches de bout en bout qui exigent d'appeler un Agent cible, de collecter ses sorties et sa trace d'exécution, puis de juger s'il a correctement terminé le workflow demandé.

À partir d'un Agent enregistré et d'un Case de benchmark, AgentBehaviorBench (ABB) exécute l'Agent au moyen d'un harness hôte de confiance. Le harness peut lancer des Agents propres à un framework ou des Agents conteneurisés, router le trafic modèle via un Model Interceptor qui protège les identifiants, enregistrer chaque input SDK et chaque response de l'Agent sous forme d'événements JSON mis à jour atomiquement, puis soumettre l'exécution terminée au DefuzeX Judge.

AgentBehaviorBench (ABB) est conçu pour rendre l'évaluation des Agents reproductible. Les Agents sont déclarés dans un registry, adaptés via des framework adapters tels que LangGraph, certifiés de `adapting` à `ready`, puis inclus dans les exécutions benchmark par défaut uniquement après une certification réussie.

Le flux d'exécution actuel est :

```text
registry.toml
-> SuiteRunner
-> BenchmarkRunner
-> DefuzeX SDK Run
-> Agent Adapter / Runtime
-> Judge Report
```

Le dépôt contient :

- `agentbench/cli` : point d'entrée terminal et affichage de progression.
- `agentbench/harness` : poignée de main SDK, exécution de suite, résultats et registry.
- `agentbench/adapter` : contrat d'adapter indépendant du framework et support LangGraph.
- `agentbench/runtime` : intégration des runtimes local et Docker.
- `resources/agents` : fixtures d'Agents de benchmark reproductibles.
- `services/model-interceptor` : intercepteur transparent pour l'accès aux model providers pendant les exécutions Docker.

![AgentBehaviorBench (ABB) framework](../figures/framework.png)

## Installation

AgentBehaviorBench (ABB) requiert Python 3.10 ou une version ultérieure ainsi que le SDK Python DefuzeX. Le SDK fournit le benchmark protocol utilisé par AgentBehaviorBench (ABB) : il analyse les benchmark requirements, crée des DefuzeX Cases, pilote chaque input SDK, enregistre les preuves et soumet les exécutions terminées pour jugement.

Créez et activez un environnement virtuel depuis le workspace parent qui contient ce dépôt :

```powershell
cd <workspace-root>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Installez AgentBehaviorBench (ABB) en mode editable :

```powershell
python -m pip install -e .\defuzeX_AgentBench
```

### Build interne du SDK

Ce dépôt dépend actuellement de la branche `dev` du SDK DefuzeX interne. Tant que le SDK n'est pas publié pour une installation package normale, si `Defuze-SDK` n'a pas encore été cloné localement, clonez-le depuis la branche `dev` du SDK (`https://github.com/DefuzeX-AI/Defuze-SDK/tree/dev`) à côté de `defuzeX_AgentBench`, puis installez-le dans le même `.venv` :

```powershell
cd <workspace-root>
git clone --branch dev --single-branch https://github.com/DefuzeX-AI/Defuze-SDK
python -m pip install -e .\Defuze-SDK
python -m pip install -e .\defuzeX_AgentBench
```

Un checkout source typique place `Defuze-SDK` et `defuzeX_AgentBench` comme répertoires frères sous le même workspace parent, tous deux installés en mode editable.

> [!NOTE]
> PAT signifie Personal Access Token. Si le dépôt interne du SDK DefuzeX est privé, GitHub peut demander un PAT lors du clone en HTTPS. Traitez le PAT comme un mot de passe : ne le placez pas dans les fichiers source, les exemples README, les notebooks ni les fichiers `.env` commités.

## Utilisation

Après avoir installé AgentBehaviorBench (ABB), lancez-le depuis le benchmark workspace avec le launcher script :

```powershell
cd <workspace-root>
.\.venv\Scripts\Activate.ps1
python .\run_agentbench.py
```

Vous pouvez aussi exécuter le package directement depuis le dépôt AgentBehaviorBench (ABB) :

```powershell
cd <workspace-root>\defuzeX_AgentBench
python -m agentbench
```

Pour enregistrer une exécution et inspecter les événements benchmark en direct dans le result viewer local, passez un chemin de sortie :

```powershell
python -m agentbench --output results\result.json
```

Sans `--output`, AgentBehaviorBench (ABB) s'exécute dans le terminal et ne crée pas d'artefact de résultat JSON. Avec `--output`, AgentBehaviorBench (ABB) écrit un fichier de résultat JSON mis à jour atomiquement et démarre le viewer local afin que vous puissiez actualiser et inspecter les événements pendant l'exécution du benchmark.

Définissez une clé API DefuzeX lorsque vous utilisez les Case ou Judge providers officiels :

```powershell
$env:DEFUZEX_API_KEY = "dfx_<public-id>.<secret>"
```

Exécutez la suite de tests :

```powershell
python -m pytest
```

Pour plus d'instructions destinées aux Agents, commencez par [AGENTS.md](../AGENTS.md). Le guide de documentation plus complet se trouve dans [docs/AGENTS.md](../docs/AGENTS.md).

## Comment ajouter des Agents au test

Si vous voulez ajouter votre propre Agent au benchmark, demandez à un agent de lire [docs/How To Add Agent.md](../docs/How%20To%20Add%20Agent.md) et de suivre le flux d'onboarding qui y est documenté.

AgentBehaviorBench (ABB) fournit les éléments nécessaires pour transformer un projet d'Agent externe en cible de benchmark répétable : discovery fondée sur le registry, framework adapters, support du Docker runtime, routage des identifiants modèle via le Model Interceptor, result artifacts mis à jour atomiquement, visualisation locale des résultats et certification de `adapting` à `ready`. Cela vous donne une manière cohérente de comparer des Agents sur les mêmes DefuzeX Cases tout en gardant le runtime behavior, les outputs et les judgment evidence inspectables.

## Citation et licence

MIT License. Voir [LICENSE](../LICENSE).

Si notre travail vous est utile, veuillez le citer comme suit :
