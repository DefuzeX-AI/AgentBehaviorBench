# Ajouter un Agent

[English](../How%20To%20Add%20Agent.md) | Français | [日本語](How%20To%20Add%20Agent.ja.md) | [中文](How%20To%20Add%20Agent.zh-CN.md) | [한국어](How%20To%20Add%20Agent.ko.md)

Suivez ce parcours : **environnement → import → configuration → contrôle statique →
test local → KUMA → view → livraison ou certification**. Exécutez les commandes à
la racine de ce dépôt ABB, dans son environnement virtuel. Remplacez `SOURCE`,
`AGENT_ID`, `NN-name` et les chemins par les valeurs réelles de votre exécution.

Un assistant de programmation doit d'abord lire `AGENTS.md`, l'issue d'intégration
et les instructions amont. Notez le périmètre autorisé, le dépôt courant et
`git status` ; préservez le travail sans rapport. Le README seul ne prouve pas
que l'Agent fonctionne.

**Quand s'arrêter :** si l'utilisateur demande une validation étape par étape,
présentez commande, résultat, chemin des preuves et étape suivante, puis attendez
son accord. Sinon, poursuivez le travail autorisé sans redemander à chaque contrôle.
Avant une nouvelle opération payante/externe, vérifiez que l'autorisation couvre
les appels modèle et l'envoi du contexte source, du profil et des preuves aux
services configurés. Une autorisation déjà donnée reste valable. Arrêtez les étapes
dépendantes si des identifiants ou décisions manquent, si le déploiement n'est pas
pris en charge ou si un échec reste inexpliqué. Conservez les acquis. N'affichez
jamais les clés ou le contenu de `.env`. Un contrôle n'est pas forcément une
demande de permission.

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
python -m agentbench --help
python -m agentbench sdk list
docker info
```

`sdk list` doit afficher kuma ; `docker info` doit réussir avec le même utilisateur
qu’ABB. Le téléchargement et la génération de configuration ne nécessitent pas
Docker, contrairement à `-c`. Les installations du SDK sur l’hôte et dans l’image
d’évaluation sont distinctes.

Vérifiez le harness avant de configurer les services payants :

```bash
python -m examples.offline_demo --output results/offline-demo.json
```

Résultat attendu : `Case execution: 1/1 completed | Judge: pass=1`. Conservez le
chemin exact `OFFLINE_RESULT=`. Cette démo echo déterministe n'utilise ni Docker,
ni clé, ni modèle et ne teste pas votre Agent. En cas d'échec, corrigez d'abord
l'environnement hôte. Contrôle : indiquez dépôt/révision, découverte CLI/SDK et
résultat de la démo. La découverte du SDK ne prouve pas la prise en charge de
l'intégration (section 2).

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

## 2. Importer la source, puis générer la configuration

Commencez par l'import seul, avant tout appel modèle :

```bash
python -m agentbench agent add https://github.com/owner/repository
```

`SOURCE` désigne le dépôt HTTPS lui-même, pas un fichier ni une URL `/tree/branch`,
ou un répertoire local absolu comme `/absolute/path/to/local-agent` ou
`C:\work\local-agent` sous PowerShell. Aucun `-d` n'est nécessaire. GitHub utilise
la révision de la branche par défaut ; il n'existe pas d'option `--revision`.
L'import local exclut `.git` et enregistre une empreinte SHA-256. Les appels suivants
avec la même source canonique réutilisent l'unité sans recopier une source locale modifiée.

**Contrôle — import terminé :** notez le chemin réel et la révision de
`source-manifest.json`. Lisez l'entrée native, les prompts, outils, schémas d'entrée
et d'état, l'appelant UI, les contraintes Python et le verrou de dépendances.
Identifiez les services et l'interface déployée : un graphe texte n'est pas une UI
d'import PDF. L'import n'enregistre pas encore un Agent exécutable. Ne contournez
pas `agent add` en plaçant une implémentation de remplacement dans le registre.

Une fois le déploiement compris, générez avec la même source :

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view
```

`-b` planifie, génère, valide et enregistre `adapting` ; il **ne construit pas Docker**.
KUMA récupère un catalogue récent avant la planification. Vérifiez objectif,
disponibilité, version exacte et capacités de preuve, puis conservez l'instantané.
Ne copiez pas l'ID de stratégie d'un autre Agent. Si la récupération échoue, corrigez
les identifiants ou le réseau avant de poursuivre, sans inventer de sélection.

Si le plan demande des précisions, fournissez des réponses factuelles dans un
fichier UTF-8 local puis reprenez :

```bash
python -m agentbench agent add https://github.com/owner/repository -b --sdk kuma --no-view --answers answers.txt
```

Décrivez la conversion texte/entrée native, le cycle de session, les fonctions UI
exclues, services et dépendances. N'inventez pas de données métier. Avant de
réessayer, consultez `build-result.json` et l'étape en échec dans `steps/`. Les fichiers
terminés sont conservés et revalidés ; les conflits manuels bloquent la génération.
N'effacez pas les acquis et ne répétez pas les appels payants sans corriger la cause.

**Limite de cette révision :** le SDK `local` sait évaluer, mais n'implémente pas
les exigences/validations d'intégration. `add -b --sdk local` échoue avec
`Selected SDK has no onboarding requirements and validation`. Générez ici avec
KUMA, puis utilisez l'évaluation locale de la section 5. Sans identifiants KUMA,
arrêtez la génération automatique ; ajouter ces interfaces au SDK local est un
changement de code distinct. Un correctif d'un autre checkout n'est pas forcément présent ici.

Le raccourci suivant convient uniquement à un déploiement déjà compris et à une
génération/certification autorisée sans approbation intermédiaire :

```bash
python -m agentbench agent add https://github.com/owner/repository -b -c --sdk kuma --no-view
```

`-c` construit et exécute la certification : ce n'est pas un contrôle statique,
et des frais peuvent s'appliquer. Il accepte aussi des fichiers préparés manuellement.
La génération automatique prend actuellement en charge LangGraph ; ne rebaptisez
pas un framework incompatible pour le faire accepter.

| Option | Rôle |
| --- | --- |
| `--sdk kuma` / `--sdk local` | Sélection explicite ; découverte ne signifie pas prise en charge de la génération. |
| `--no-view` | Conserver les résultats sans lancer le visualiseur. |
| `--build-model MODEL` | Modèle de génération, avec sorties structurées strictes. |
| `--model MODEL` | Modèle de l'Agent pendant la certification. |
| `--answers answers.txt` | Réponses à un plan précédent. |
| `--with-observe` | Avec `-b`, produire les indications d'entrée native pour observe. |
| `--build-settings settings.toml` | Surcharges dans une table `[build]`. |
| `-y` | Supprimer la confirmation CLI seulement si l'exécution est déjà autorisée. |

Priorité du modèle de génération : `--build-model`, settings `model`,
`OPENROUTER_BUILD_MODEL`, puis `OPENROUTER_MODEL`. Consultez les
[paramètres fournis (anglais)](../../agentbench/onboarding/build_agent_env/openrouter_provider/assets/settings.toml)
avant de modifier budgets ou nouvelles tentatives.

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

## 4. Examiner et valider avant l'exécution

**Contrôle — configuration :** examinez chaque fichier, pas seulement le message
de succès. Vérifiez la provenance et les frontières suivantes :

- Le descripteur doit viser le graphe original. Si `langgraph.json` manque,
  consignez explicitement l'ajout d'un descripteur minimal tel que `abb-langgraph.json`
  dans la provenance, sans réécrire le graphe.
- Le binding expose une fabrique synchrone sans argument et appelle le véritable
  Agent. Préservez `config`/callbacks, exceptions et sortie brute. Reproduisez
  l'ajout des messages et l'agent actif de l'UI native ; isolez les Cases et nettoyez
  à la fermeture. Ni conversation globale mutable, ni erreurs masquées.
- Le champ de sortie doit extraire la vraie réponse, les preuves gardant l'état
  complet. Arrêtez si plusieurs champs métier obligatoires ne peuvent pas être
  fournis honnêtement depuis le texte.
- Installez le verrou amont avec un interpréteur compatible, séparément des
  dépendances ABB hôte. Pour uv, projet, verrou et interpréteur doivent correspondre ;
  `/opt/venv` évite une installation dans une source en lecture seule. Vérifiez pip.
- Examinez la configuration **après overlay SDK**, ses routes ajoutées et les COPY
  des fichiers binding/runtime. Le TOML externe seul ne suffit pas.
- Le profil décrit les outils réels, les données à fournir et les opérations
  absentes. KUMA exige actuellement `input_type: text`, les trois titres anglais
  exacts et un groupe du catalogue. N'annoncez pas navigation, import, exécution
  de code ou persistance sans implémentation.

Après correction manuelle, utilisez le validateur statique de l'intégration :

```bash
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
unit = Path("resources/agents/NN-name")
print(validate_unit(unit, plugin))
PY
```

Ce contrôle utilise les fichiers et le parseur SDK installé, hors ligne. Il
n'exécute pas l'Agent et ne consulte/valide pas le catalogue en direct sans contexte
fourni. La génération valide avec son instantané récent ; KUMA vérifie à nouveau
les règles du service avant exécution. Un succès statique n'est pas une exécution.
Testez les bindings complexes hors ligne : frontière adapter réelle, isolation,
transmission de config, asynchrone si disponible et exceptions. Les fixtures doivent
être autonomes ou signaler explicitement l'absence d'une unité optionnelle.

## 5. Exécuter un Case de contrôle local

Pour un Agent texte configuré, commencez petit :

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk local --no-view
```

Cela exécute le véritable Agent Docker avec interception modèle, Cases texte fixes
et Judge local. Docker et un accès modèle sont requis ; des tokens peuvent être
facturés. Aucun identifiant/crédit KUMA n'est nécessaire. Ce n'est pas la démo echo
hors ligne sans identifiants. Les Cases fixes ne proviennent pas du profil et ne
couvrent pas forcément le traitement d'articles ou les transferts entre spécialistes.

**Contrôle — local :** conservez chemin Suite, répertoire détaillé, réponses,
état des traces et rapport Judge. Exigez exécution réussie et acceptation hôte avant
de dire l'intégration exécutable. Ouvrez view après ce premier essai, même en échec
(section 7). Un import ou un test à fixtures ne remplace pas une vraie exécution.

Si les Cases génériques omettent le contexte requis, utilisez éventuellement
`observe` avec une entrée native fondée sur la source, après autorisation.
Pour un binding texte, `native-input.json` contient une chaîne JSON ; sinon,
respectez son schéma. Fournissez le vrai extrait ou les données nécessaires,
pas seulement « lire le texte fourni » sans texte.

```bash
python -m agentbench observe AGENT_ID --input native-input.json
```

Observe enregistre l'exécution sans génération de Case/Judge KUMA ; modèle et
outils peuvent coûter. Cela ne transforme pas un benchmark échoué en succès.
Si l'utilisateur demande directement KUMA, passez à la section 6 après le contrôle
statique et signalez que le contrôle local a été omis, le cas échéant.

## 6. Lancer une nouvelle évaluation KUMA

Examinez le profil déployé et la stratégie actuelle, vérifiez l'autorisation des
appels KUMA/modèle et de l'envoi des preuves, puis lancez un Case :

```bash
python -m agentbench evaluate AGENT_ID --cases 1 --sdk kuma --no-view
```

Un succès local ne prouve pas la compatibilité KUMA. Le profil modifié affecte les
futurs Cases seulement. Vérifiez données requises et opérations réellement
possibles dans le Case généré. Conservez les défauts du Case à côté des problèmes
Agent ; ne modifiez jamais les entrées, réponses ou preuves originales pour réussir.

Suivez la même exécution : génération, appels Agent, soumission, polling Judge.
L'acceptation d'une requête asynchrone n'est pas un verdict ; ne lancez pas de
second essai pendant l'attente. Après timeout/erreur, examinez l'état sauvegardé
de complétion et de récupération avant reprise. Respectez la sûreté de rejeu et
les effets des outils, sans modifier les indicateurs de sécurité pour forcer la
reprise. Un nouvel `evaluate` crée une nouvelle Suite, généralement de nouveaux
Cases : ce n'est pas un rejeu contrôlé du précédent.

## 7. Ouvrir view et distinguer les résultats

Ouvrez view après le premier essai local, après KUMA et avant diagnostic, nouvelle
tentative ou déclaration de fin. Sans interface graphique, examinez les mêmes
JSON/traces et précisez que l'UI n'a pas été vérifiée.

```bash
python -m agentbench view results/suites/ACTUAL_SUITE_ID/events.json
```

Utilisez le chemin exact de `Result saved` / `Open later`. La démo hors ligne
imprime plutôt le fichier horodaté `OFFLINE_RESULT`. N'inventez pas le nom et ne
réutilisez pas une ancienne Suite. Ouvrez l'URL `View:` complète avec son chemin,
gardez le serveur actif, puis Ctrl+C pour l'arrêter. `--no-view` conserve les résultats.

Examinez **Suite → Case → chaque entrée/réponse → traces modèle/outils/transferts →
Judge et preuves → exécution/nettoyage/acceptation hôte**. Un transfert réussi
n'est pas une tâche spécialiste terminée ; une écriture déclarée n'est pas une
écriture effectivement observée.

| Preuve | Interprétation et suite |
| --- | --- |
| Exécution réussie + hôte accepté + Judge pass | Ce Case réussit ; précisez le périmètre sans généraliser. |
| Exécution réussie + hôte accepté + Judge issue | L'intégration s'exécute ; gardez le constat comportemental sans réécrire les prompts pour réussir. |
| Exception native / execution failed | Pas d'exécution réussie, même avec rapport Judge. Diagnostiquez avant promotion. |
| Traces partielles / insufficient evidence / hôte refusé | Décrivez les lacunes. OTel complete ne garantit pas tout le contenu des outils. |
| Article/données absents ou action impossible | Notez la limite Case/profil ; évaluez séparément les affirmations étayées. N'inventez pas les données. |

Dans `results/observe/<run-id>/`, consultez, s'ils existent, `run.json`,
`evaluation/case.json`, `evaluation/inputs/`, `evaluation/manifest.json` et
`evaluation/judge/report.json`. Un fichier absent peut signaler une phase inachevée ;
n'inférez pas de verdict. Un code de sortie non nul peut venir d'un Judge issue,
pas d'un crash. Un export JSON seul n'est pas une archive complète autonome.

## 8. Décider si la certification est nécessaire

`evaluate` ne promeut pas le registre et ne change pas son nombre de Cases. Si
l'objectif inclut la sélection par `run`, vérifiez ce nombre et l'autorisation
d'une exécution supplémentaire, puis :

```bash
python -m agentbench certify AGENT_ID --sdk kuma --no-view
```

Certify exécute le nombre configuré, sans simplement approuver les anciennes
preuves. Tous les Cases terminés sans erreurs d'invocation peuvent promouvoir
`adapting` en `ready`, même avec constats Judge. Un Agent déjà ready retourne sans
nouvelle certification ; utilisez evaluate après modification. Ne forcez pas ready
pour masquer un blocage. Si l'utilisateur accepte l'intégration après évaluation,
indiquez l'état réel puis arrêtez, sans payer uniquement pour changer l'étiquette.

## 9. Diagnostiquer à la frontière qui échoue

Partez du premier échec et de ses preuves, avec un rejeu minimal hors ligne si
possible. Changez un seul facteur : graphe/binding, un/plusieurs appels outils,
synchrone/asynchrone, dépendances verrouillées/environnement hôte. Gardez les scripts
hors de l'unité distribuée. Séparez correction de déploiement et changement de
comportement amont ; proposez ce dernier séparément. Ne désactivez pas l'interception,
ne masquez pas les erreurs et ne fabriquez pas de résultats d'outils.

| Symptôme | Contrôle, action et arrêt |
| --- | --- |
| agentbench absent ou mauvais checkout importé | Activez le bon venv, utilisez `python -m agentbench`, vérifiez l'installation editable avant de modifier l'Agent. |
| Docker indisponible, permission ou architecture | Vérifiez `docker info` avec le même utilisateur et la plateforme image ; obtenez la permission requise sans contourner l'isolation. |
| SDK découvert sans interfaces onboarding, ou import kuma absent | Découverte n'est pas validation. Choisissez un SDK capable de générer et installez ses dépendances épinglées. |
| Catalogue/authentification/réseau | Vérifiez présence des clés, priorité shell, endpoint et réseau sans révéler les secrets ; arrêtez la génération jusqu'à résolution. |
| Sortie structurée refusée, needs_input, conflit | Consultez plan/étapes ; corrigez modèle de génération, réponses factuelles ou fichiers après examen. Réessayez seulement l'étape concernée. |
| uv projet/verrou, pip absent, import conteneur | Vérifiez Python amont, chemin du verrou, interpréteur, isolation et COPY. La validation statique ne prouve pas l'installation. |
| TOML externe valide mais erreur overlay | `tool_routes = []` peut entrer en conflit avec `[[llm_interception.tool_routes]]` ajouté ; retirez la déclaration vide inutile après examen, sans enlever routes nécessaires/interception. |
| INVALID_CHAT_HISTORY avec transferts multiples | Associez chaque tool-call ID à un ToolMessage et rejouez le graphe hors ligne. Un transfert simple réussi ne valide pas les transferts parallèles. |
| Judge signale absence de reprise ou action externe déclarée | Vérifiez si le modèle a reçu l'erreur et si l'outil existe/a été exécuté. Distinguez texte, état et limites de preuve. |
| Visualiseur vide, inaccessible ou ancien résultat | Construisez web/dist, utilisez URL/chemin exacts et serveur actif ; vérifiez les ports. Ne relancez pas l'évaluation payante pour réparer view. |

Article Explainer illustre ces distinctions : dialogue local fonctionnel, une
exécution KUMA échouant sur des transferts parallèles natifs, une autre terminée
avec constats comportementaux, et des Cases sans texte d'article. Ces exemples
ne garantissent rien pour une autre révision, un autre modèle ou Case. Ne réutilisez
pas leur ID de stratégie sans examen du catalogue.

## 10. Liste de livraison et compte rendu

Indiquez source/révision, unité, fichiers générés/corrigés, commandes, chemins
réels des preuves/view, puis séparément exécution local/KUMA, acceptation hôte,
Judge, capacités non testées, défauts connus, registre et état Git (local,
commit/push/PR). Séparez code/docs de `.venv`, secrets, images, caches, verrous et
résultats. Ne commitez aucun secret.

Arrêtez quand les preuves couvrent l'objectif convenu. Un constat comportemental
peut être un résultat valable du benchmark, pas une intégration inachevée. Ne
répétez pas jusqu'à un succès chanceux et ne réparez pas silencieusement l'Agent.
Un commit ou une PR demandés constituent une étape autorisée distincte, avec diff examinable.

Voir [dépannage (anglais)](../Troubleshooting.md), [problèmes connus (anglais)](../Documentation-Issue-Audit.md)
et [générateur (anglais)](../../agentbench/onboarding/build_agent_env/README.md).
