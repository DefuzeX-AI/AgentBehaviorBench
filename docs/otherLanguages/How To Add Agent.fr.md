# Ajouter un Agent

[English](../How%20To%20Add%20Agent.md) | Français | [日本語](How%20To%20Add%20Agent.ja.md) | [中文](How%20To%20Add%20Agent.zh-CN.md) | [한국어](How%20To%20Add%20Agent.ko.md)

Suivez cet ordre : **préparer l’environnement → lancer la commande → examiner les
fichiers créés**. Un utilisateur ou un assistant de programmation peut suivre le
même parcours. Sauf changement explicite, exécutez les commandes à la racine du dépôt ABB.

## 1. Préparer l’environnement

### Installer ABB et les dépendances hôte

Terminez [l’installation d’ABB](README.fr.md). Il faut Git, Python 3.10+ avec un
environnement virtuel activé et, pour la certification, Docker accessible à votre
utilisateur. Installez les dépendances de validation du SDK sur l’hôte :

```bash
source .venv/bin/activate
python -m pip install -e .
python -m pip install -r agentbench/sdk/plugin/kuma/requirements.txt
git --version
agentbench sdk list
docker info
```

`sdk list` doit afficher kuma ; `docker info` doit réussir avec le même utilisateur
qu’ABB. Le téléchargement et la génération de configuration ne nécessitent pas
Docker, contrairement à `-c`. Les installations du SDK sur l’hôte et dans l’image
d’évaluation sont distinctes.

### Configurer les identifiants et les modèles

Copiez le modèle uniquement si `.env` n’existe pas :

```bash
test -f .env || cp .env.example .env
```

Modifiez-le localement :

```dotenv
KUMA_API_KEY=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=openai/gpt-4.1-mini
# Optional separate model for integration-file generation:
# OPENROUTER_BUILD_MODEL=
# Add the tool credentials required by your Agent, for example:
# TAVILY_API_KEY=
```

- **Clé KUMA** : accès au catalogue de stratégies, génération des Cases et Judge.
  ABB accepte aussi DEFUZEX_API_KEY ; KUMA_API_KEY non vide est prioritaire.
- **Clé et modèle OpenRouter** : génération des fichiers et exécution de l’Agent.
  Le modèle de génération doit prendre en charge les **sorties structurées strictes**.
  Un modèle de conversation fonctionnel ne suffit pas forcément. Le nom montré est
  un exemple de configuration, pas une valeur par défaut implicite du programme.
- **Dépendances de l’Agent** : préparez les clés d’outils, données et services externes
  selon son dépôt. Installer un pilote ne démarre pas une base de données ; télécharger
  un Agent ne déploie pas tous ses services.

Les liens pour obtenir les clés figurent dans le
[guide de configuration (anglais)](../../README.md#configure-a-real-evaluation).
Les variables exportées par le shell priment sur .env ; --env-file PATH choisit un
autre fichier. ABB résout les identifiants déclarés et ne monte pas le fichier .env
entier dans les conteneurs. Ne placez pas de secrets dans le code ou les fichiers générés.

### Préparer le navigateur si nécessaire

Installez npm et Node.js **20.19+ dans la branche 20.x, ou 22.12+**, puis :

```bash
cd web
npm ci
npm run build
cd ..
```

Cela prépare le visualiseur ABB, pas les dépendances navigateur ou Node/MCP de
l’Agent. Ajoutez --no-view à la commande suivante pour une exécution sans interface,
qui ne nécessite ni Node ni web/dist.

## 2. Lancer la commande d’ajout

`SOURCE` peut être le dépôt GitHub HTTPS de l’Agent ou un répertoire local absolu.
Pour GitHub, utilisez le dépôt lui-même, pas une URL de fichier ou /tree/branch :

```bash
agentbench agent add https://github.com/owner/repository -b -c
```

Pour une source locale :

```bash
agentbench agent add /chemin/absolu/vers/local-agent -b -c
```

ABB copie le répertoire dans `agent/`, omet les métadonnées `.git` et enregistre
une empreinte SHA-256 comme révision. Les chemins relatifs sont refusés. Les appels
ultérieurs avec le même chemin canonique réutilisent l’unité importée.

- `-b` : génère et valide les fichiers d’intégration, puis enregistre l’Agent comme
  adapting. Cela ne signifie pas « construire immédiatement l’image Docker ».
- `-c` : construit/exécute l’Agent via la certification. La réussite de l’exécution
  des Cases configurés permet le passage à ready ; le Judge peut néanmoins signaler des problèmes.

ABB importe les sources, planifie l’intégration, sauvegarde chaque fichier validé,
puis demande confirmation pour la certification. Génération et certification peuvent
être facturées. La configuration automatique prend actuellement en charge **LangGraph** ;
les autres frameworks nécessitent d’abord un adaptateur compatible.

Pour examiner les fichiers avant la certification, omettez -c :

```bash
agentbench agent add https://github.com/owner/repository -b
```

Sans ces deux options, agentbench agent add SOURCE importe et liste seulement les
fichiers de configuration, sans générer d’intégration ni enregistrer d’Agent exécutable.
GitHub conserve la révision de la branche par défaut ; une source locale conserve
l’empreinte du contenu copié. Il n’existe pas encore d’option --revision.

| Option | Utilité |
| --- | --- |
| `--no-view` | Certifier sans visualiseur ; les résultats sont sauvegardés. |
| `--build-model MODEL` | Modèle de génération des fichiers. |
| `--model MODEL` | Modèle utilisé par l’Agent lors de la certification. |
| `--answers answers.txt` | Réponses textuelles aux questions du plan précédent. |
| `--with-observe` | Avec -b, générer les invites de saisie native pour observe. |
| `--build-settings settings.toml` | Remplacer des réglages via une table [build]. |

Priorité du modèle de génération : --build-model, model du fichier de réglages,
OPENROUTER_BUILD_MODEL, puis OPENROUTER_MODEL. Consultez les
[valeurs fournies](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)
avant de modifier budgets, délais ou tentatives.

## 3. Comprendre les fichiers

L’unité Agent se trouve sous `resources/agents/NN-name/`. La commande génère les
fichiers d’intégration autour du code importé ; inutile de tous les écrire à la main avant.

```text
resources/agents/NN-name/
├── agent/                   # Instantané de source amont ou locale importée
├── agent.toml               # ABB execution configuration
├── bindings/                # Boundary between ABB and the native Agent
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

### `bindings/*.py` — la frontière avec l’Agent natif

Expose une fabrique synchrone sans argument renvoyant le véritable objet invocable.
Le binding adapte les formats selon le code source et gère le nettoyage du cycle
de vie. Il ne doit ni inventer des réponses ni substituer un Agent simplifié.
Une syntaxe Python valide ne prouve pas que le graphe peut être chargé et exécuté.

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

## Après la génération

Si vous avez utilisé -b seul, préparez une entrée JSON conforme au binding, puis :

```bash
agentbench observe AGENT_ID --input native-input.json
agentbench evaluate AGENT_ID --cases 1 --no-view
agentbench certify AGENT_ID --no-view
```

Utilisez l’identifiant généré. observe exécute modèle/outils sans Case/Judge KUMA,
mais ces appels peuvent être facturés. evaluate --cases 1 ne change pas le nombre
au registre ; certify utilise ce nombre, à vérifier avant. Un Agent déjà ready n’est
pas recertifié ; utilisez evaluate pour vérifier vos changements ultérieurs.

Si la génération s’arrête, lisez build-result.json et l’étape en échec, corrigez puis
relancez la même commande -b. Les fichiers terminés sont conservés et revalidés ;
les conflits manuels arrêtent le processus sans écrasement. Utilisez --answers answers.txt
pour répondre aux questions du plan.

Consultez le [dépannage (anglais)](../Troubleshooting.md), les
[problèmes connus (anglais)](../Documentation-Issue-Audit.md) et le
[guide développeur (anglais)](../../agentbench/onboarding/build_agent_env/README.md).
