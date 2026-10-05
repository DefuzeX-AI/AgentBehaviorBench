# Ajouter un Agent

[English](../How%20To%20Add%20Agent.md) | Français | [日本語](How%20To%20Add%20Agent.ja.md) | [中文](How%20To%20Add%20Agent.zh-CN.md) | [한국어](How%20To%20Add%20Agent.ko.md)

[Démarrer ABB — anglais](../Guide.md) · [Référence CLI](cli.fr.md) · [Registre](Registry.fr.md)

Depuis la racine du dépôt ABB, avec son environnement virtuel actif, préparez l’environnement, importez la source, générez les fichiers, puis examinez et testez l’Agent. Remplacez SOURCE, AGENT_ID, NN-name et les chemins par vos valeurs.

## 1. Préparer l’environnement

Installez Git et Python 3.10+, puis suivez le guide de démarrage ci-dessus. Docker doit être accessible à votre utilisateur pour exécuter et certifier l’Agent. Pour la génération ou validation KUMA, installez KUMA dans le même environnement virtuel qu’ABB :

```bash
python -m pip install -e .
python -m pip install "kuma-defuzex[otel]>=0.3.3"
git --version
agentbench --help
agentbench sdk list
docker info
```

`sdk list` énumère les plugins sans vérifier leurs dépendances. L’import et la génération ne nécessitent pas Docker. Les installations SDK sur l’hôte et dans le conteneur sont distinctes.

Copiez `.env.example` vers `.env` seulement si ce dernier n’existe pas, puis modifiez-le localement. KUMA utilise KUMA_API_KEY (ou DEFUZEX_API_KEY) ; la génération utilise OpenRouter et un modèle à sorties structurées strictes :

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate generation model:
# OPENROUTER_BUILD_MODEL=
```

Configurez séparément le modèle de l’Agent : LangGraph peut utiliser OpenRouter, DeepSeek ou GLM ; les Agents ACP natifs utilisent leurs identifiants déclarés. Consultez le guide de démarrage. `--build-model` choisit le modèle de génération ; `--model`, le modèle cible de substitution ABB pour la certification. Les variables du shell priment sur `.env`. Ne placez pas de clés dans les sources ou fichiers générés.

Pour le visualiseur, utilisez npm avec Node.js 20.19+ sur 20.x ou 22.12+, puis construisez le frontend. Une évaluation avec `--no-view` ne nécessite ni Node ni `web/dist`.

```bash
cd web
npm ci
npm run build
cd ..
```

## 2. Importer la source et générer la configuration

SOURCE est l’URL HTTPS d’un dépôt GitHub, pas une page de fichier ou branche, ou un répertoire local absolu. GitHub importe la branche par défaut, sans option `--revision`. L’import local exclut `.git` et enregistre une empreinte. Importez d’abord :

```bash
agentbench agent add https://github.com/owner/repository
```

`agent add` crée aussi `ground_truth/.gitkeep` à côté de `agent/`, y compris lors de la réutilisation d’une unité importée. Ce fichier permet à Git de conserver le répertoire ; les défauts confirmés et leurs preuves restent à préparer manuellement selon [Ground Truth](../Ground%20Truth.md).

Générez ensuite avec la même source. Répéter l’import sans `-b` ou `-c` signale un doublon ; ces options réutilisent l’unité correspondante sans actualiser une source modifiée. Pour une source locale, utilisez `/absolute/path/to/local-agent` ou `"C:\work\local-agent"` sous PowerShell.

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma
```

`-b` prend en charge LangGraph et ACP, génère et valide les fichiers, puis enregistre `adapting`, sans construire Docker. KUMA récupère le catalogue courant avant la planification. Le SDK `local` sait évaluer mais n’a pas de validation d’intégration : utilisez KUMA ici. Si des précisions sont nécessaires, écrivez des réponses factuelles dans `answers.txt` UTF-8 et répétez avec `--answers answers.txt`. Les fichiers valides sont conservés après un échec ; consultez `build-result.json` avant de réessayer.

```bash
agentbench agent add https://github.com/owner/repository -b --sdk kuma --answers answers.txt
```

## 3. Comprendre les fichiers

L’unité Agent se trouve sous `resources/agents/NN-name/`. La commande génère les
fichiers d’intégration autour du code importé ; inutile de tous les écrire à la main avant.

```text
resources/agents/NN-name/
├── agent/                   # Instantané de source amont ou locale importée
├── agent.toml               # ABB execution configuration
├── bindings/                # LangGraph binding; not required for native ACP
├── Dockerfile               # Agent image build instructions
├── .dockerignore            # Files excluded from the image build context
├── requirement.md           # Evaluation description for the selected SDK
└── evaluation/              # Optional referenced schemas or fixtures
```

### `agent/` — le code de l’Agent

Ce répertoire contient l’instantané importé, son graphe, son raisonnement et ses
outils réels. Gardez l’intégration ABB à l’extérieur pour ne pas remplacer discrètement
le comportement d’origine.

### `agent.toml` — démarrage et invocation

Déclare l’identifiant, le framework, la révision, la construction et le lancement
Docker, l’adaptateur, les mappings d’entrée/sortie, l’environnement et les routes
modèle/outils. Vérifiez chemins et entrées obligatoires. Déclarer une route ou une
variable n’implémente pas un outil et ne démarre pas un service.

### `bindings/*.py`

Pour LangGraph, le binding expose une fabrique synchrone sans argument, renvoyant le véritable Agent invocable et adaptant les entrées, sorties et le nettoyage. ACP utilise la commande et le protocole natifs configurés dans `agent.toml`, sans fabrique Python obligatoire. Préservez le comportement de l’Agent.

### `Dockerfile` — les dépendances du conteneur

Installe les dépendances Python/système et copie code, binding et configuration.
Vérifiez architecture CPU, interpréteur, emplacements inscriptibles et besoins
navigateur/Node propres à l’Agent. L’overlay KUMA utilise actuellement python -m pip
pour installer le SDK ; cet interpréteur doit donc disposer de pip.

### `.dockerignore` — exclusions de construction

Exclut secrets, environnements virtuels hôte, caches et résultats tout en conservant
les sources/configurations nécessaires. -b le produit à partir du modèle ABB.

### `requirement.md` — le périmètre de l’évaluation

Décrit l’usage, les comportements observables, les outils déployés et les limites.
KUMA exige un en-tête YAML et les sections Production Use Scenario, Behaviors to Test,
et Known Limitations or Prohibited Behaviors. Le groupe de stratégies vient du
catalogue actuel du SDK.

Décrivez les capacités présentes, pas les extensions possibles. Un Agent de recherche
peut expliquer un calcul, sans pouvoir exécuter un échantillonneur ou sauvegarder un
fichier. Précisez comment traiter les capacités ou entrées manquantes. Le Profile guide
l’évaluation ; il n’ajoute pas d’outils, ne change pas le prompt système ni les Cases sauvegardés.

### `evaluation/` — fichiers complémentaires facultatifs

Nécessaire seulement si le Profile référence des schémas ou fixtures. Aucun répertoire
obligatoire ni input-contract.json imposé. Le chemin officiel de génération KUMA accepte
actuellement du texte ; la validation locale d’un schéma structuré ne prouve pas sa prise
en charge distante. Les mappings natifs restent dans agent.toml et le binding.

### Registre et enregistrements automatiques

`resources/registry.toml`, hors de l’unité, stocke chemin, activation, état adapting/ready
et nombre case. La génération enregistre adapting, la certification contrôle la promotion,
et run choisit les Agents activés et ready.

L’importateur crée aussi **source-manifest.json automatiquement**, avec l’URL GitHub ou
le chemin local canonique et sa révision pour réutiliser l’import. C’est un enregistrement interne ABB, pas un fichier
exigé par KUMA ni à préparer par l’utilisateur. Conservez-le pour poursuivre le parcours.

Les traces de génération sont dans `cache/onboarding/<unit-name>-<path-digest>/`.
build-state.json suit le travail réutilisable ; chaque tentative conserve plan, catalogue
SDK, steps et build-result.json. Ce sont également des enregistrements automatiques,
pas des sources de l’Agent.

## 4. Examiner et valider la configuration

Vérifiez l’entrée, les mappings natifs, dépendances, identifiants déclarés et routes à partir du code réel. LangGraph : descripteur et fabrique ; ACP : commande native et session. Le profil décrit les outils réels, données requises et limites. Après modification manuelle, utilisez le validateur (exemple Bash) :

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/NN-name"), plugin))
PY
```

Ce contrôle vérifie les fichiers et le parseur SDK sans exécuter l’Agent. Sans contexte de catalogue fourni, il ne vérifie pas le catalogue distant courant. Une validation statique ne prouve pas l’exécution.

## 5. Exécuter un Case de contrôle local

Activez `enabled = true` dans le registre, puis exécutez un Case. `local` utilise des Cases texte génériques et un Judge local, sans crédit backend KUMA. L’Agent et le Judge peuvent néanmoins appeler un modèle payant. Ce test ne certifie pas l’intégration et n’est pas une évaluation comportementale KUMA.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

## 6. Évaluer avec KUMA

Après le contrôle local, KUMA génère un nouveau Case, collecte les preuves et obtient un rapport Judge. Cela appelle les services modèle configurés et l’API KUMA.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

## 7. Consulter les résultats

Utilisez le fichier exact indiqué par `Result saved`, ouvrez l’URL `View:` complète et laissez la commande active. Conversation montre les entrées/sorties, Judge les constats, Timing l’exécution et OTel. Fin d’exécution et verdict sont distincts : `issue` est un constat ; `insufficient_evidence` seul n’est pas un défaut confirmé.

```bash
agentbench view results/suites/SUITE_ID/events.json
```

## 8. Certifier l’intégration

Pour rendre un Agent `adapting` disponible à `run`, certifiez-le tout en le laissant activé. La certification exécute de nouveaux Cases selon le registre, sans approuver les anciens résultats. Des Cases achevés sans erreur d’invocation permettent `ready`, même avec des constats Judge. Un Agent déjà ready n’est pas réexécuté ; utilisez `evaluate`. `agent add -c` exige des fichiers valides générés ou manuels et n’implique pas `-b`.

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
```

## 9. Résultats, reprises et dépannage

Plans, Cases et événements : `results/suites/SUITE_ID/` ; détails des exécutions généralement : `results/observe/RUN_ID/`. Utilisez les chemins affichés. `--results-dir DIR` choisit la racine ABB ; `evaluate --output DIR` choisit séparément les artifacts SDK.

```bash
agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view --results-dir results/my-run
```

`resume` poursuit le travail inachevé récupérable ; `retry` cible un Case inachevé. `reuse` réexécute les entrées sauvegardées et Judge, sans écraser les résultats. Les numéros commencent à 1. Le visualiseur propose Rerun this Case et Open reuse Suite. Gardez le processus du lot actif ; les requêtes incertaines ou non sûres peuvent rester bloquées.

```bash
agentbench resume results/suites/SUITE_ID
agentbench retry results/suites/SUITE_ID --agent AGENT_ID --case 1
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent AGENT_ID --case 1
```

Export JSON produit un instantané, pas toutes les traces ni un rapport HTML autonome. Conservez la Suite et les répertoires référencés. Prévisualisez avec `agentbench clean --dry-run` et arrêtez exécutions et visualiseurs avant l’archivage.

Trace UI not built : construisez `web/`. Erreurs Docker : `docker info` avec le même utilisateur. Imports SDK : installez le SDK dans l’environnement ABB. Modèle/clé : vérifiez service, modèle et priorité du shell. Planification ou needs_input : consultez le journal et fournissez des réponses factuelles.

[Référence CLI](cli.fr.md) · [Dépannage détaillé — anglais](../Troubleshooting.md)
