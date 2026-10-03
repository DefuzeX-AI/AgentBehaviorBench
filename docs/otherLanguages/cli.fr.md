# Référence CLI ABB

[English](../cli.md) | [中文](cli.zh-CN.md) | Français | [日本語](cli.ja.md) | [한국어](cli.ko.md)

[Retour au README](README.fr.md) · [Démarrer ABB — anglais](../Guide.md) · [Registre des Agents](Registry.fr.md) · [Ajouter un Agent](How%20To%20Add%20Agent.fr.md)

Cette référence décrit chaque commande, tous les arguments publics, leurs valeurs par défaut et des exemples. Installer ABB et configurer l’Agent avant toute exécution.

Remplacer AGENT_ID, SUITE_ID, CASE_ID, RUN_ID, chemins et fichiers par leurs valeurs réelles. Les numéros d’Agents correspondent à la liste affichée ; les Cases commencent à 1. OPTIONS désigne les options du tableau. Toutes les commandes acceptent -h/--help ; agentbench sans argument lance run.

```bash
agentbench --help
agentbench evaluate --help
agentbench agent add --help
```

agent exige le sous-commande add ; sdk exige list ou show. Consulter agentbench agent --help ou agentbench sdk --help. Au niveau du groupe, seule l’option -h/--help précède le sous-commande.

## Choisir une commande

| Commande | Rôle et valeur par défaut |
| --- | --- |
| `agentbench run` | Exécuter dans une Suite tous les Agents activés et ready du registre, avec leurs budgets case et step. Confirmer la sélection avant exécution. |
| `agentbench evaluate` | Générer des Cases indépendants pour un Agent activé, l’exécuter, recueillir les preuves et obtenir les résultats du Judge via le SDK. Aucun changement du statut du registre. |
| `agentbench agent add` | Importer un dépôt GitHub ou un répertoire local. Sans -b/-c : import et liste des fichiers. -b génère l’intégration ; -c certifie. Les deux peuvent être combinés. |
| `agentbench certify` | Exécuter le budget de Cases d’un Agent adapting activé et le promouvoir à ready si tous terminent sans erreur d’invocation. Un constat du Judge ne bloque pas à lui seul la promotion ; pas de nouvelle exécution pour ready. |
| `agentbench observe` | Exécuter une entrée native et enregistrer sorties et traces, sans génération de Case ni Judge. Requiert actuellement Docker en mode oneshot. --list et --show sont des consultations seules. |
| `agentbench view` | Servir les résultats enregistrés dans le visualiseur local. Construire les ressources web d’abord. Ouvrir l’URL View complète et garder la commande active ; Ctrl+C l’arrête. |
| `agentbench sdk list` | Lister les noms de plugins SDK découverts. Ne vérifie pas que toutes les dépendances d’exécution sont installées. |
| `agentbench sdk show` | Charger un plugin SDK et afficher sa source, son mode d’exécution et sa sélection implicite. |
| `agentbench resume` | Continuer le travail inachevé récupérable d’une Suite avec Cases et configuration sauvegardés et identifiants actuels. Aucun nouveau Case ni réexécution volontaire des Cases terminés. |
| `agentbench retry` | Récupérer un Case inachevé dans sa Suite initiale avec les entrées originales. Selon l’état, reprendre la requête ou rejouer dès la première entrée. Les conditions de rejeu s’appliquent. |
| `agentbench reuse` | Réutiliser les entrées sauvegardées pour une nouvelle exécution, collecte de preuves et évaluation dans une Suite liée. Conserver les résultats originaux sans nouvelles entrées. Convient aux Cases terminés. |
| `agentbench clean` | Archiver l’historique non référencé de results du projet dans cache/history-trash. Conserver les Suites et artifacts référencés. Prévisualiser puis arrêter exécutions et visualiseurs avant archivage. |

## `run`

Exécuter dans une Suite tous les Agents activés et ready du registre, avec leurs budgets case et step. Confirmer la sélection avant exécution.

```text
agentbench run [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `--sdk NAME` | Choisir un nom de SDK indiqué par sdk list. Défaut fourni : kuma ; local doit être explicite. Si plusieurs plugins autorisent la sélection implicite, préciser le nom. | `--sdk kuma` |
| `--sdk-options PATH` | Lire un objet JSON d’options du SDK choisi ; défaut : aucune option explicite, valeurs définies par le SDK. | `--sdk-options sdk-options.json` |
| `--case-retries N` | Tentatives automatiques supplémentaires pour un Case récupérable en sécurité. Entier ≥ 0 ; défaut 2, zéro désactive les reprises automatiques. | `--case-retries 0` |
| `--retry-delay SECONDS` | Délai initial avant reprise, en secondes. Nombre fini ≥ 0 ; défaut 5. Les délais suivants augmentent selon la politique. | `--retry-delay 5` |
| `-y, --yes` | Ignorer la confirmation d’exécution ; par défaut, elle est demandée. | `--yes` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--results-dir DIR` | Racine des résultats ABB, créée si nécessaire. Depuis la racine du dépôt, défaut : results/. Événements : DIR/suites/SUITE_ID/events.json. Incompatible avec l’ancienne option de destination. | `--results-dir results/my-run` |
| `--output PATH` | Ancienne destination ABB. Un chemin de fichier choisit son parent sans créer le fichier ; préférer --results-dir. Depuis la racine du dépôt, défaut : results/. | `--output results/legacy.json` |
| `--no-view` | Enregistrer les résultats sans lancer le visualiseur ; par défaut, démarrer ou réutiliser celui-ci. Les ressources web doivent être construites. | `--no-view` |
| `--model MODEL` | Remplacer le modèle cible de substitution ABB ; défaut : configuration du fournisseur choisi. Les modèles ACP natifs suivent la configuration de l’Agent. | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | Ancien seuil mémoire du stockage temporaire du flux, en octets ; défaut 262144 (256 Kio). Ne tronque pas les contenus enregistrés. | `--llm-trace-max-bytes 262144` |

run n’a pas d’options --registry, --cases ou --max-steps. Modifier les budgets par Agent dans le registre ; max_steps du JSON SDK peut remplacer le budget d’étapes.

### Exemples

```bash
agentbench run --sdk kuma
agentbench run --sdk local --yes --no-view --results-dir results/smoke
```

## `evaluate`

Générer des Cases indépendants pour un Agent activé, l’exécuter, recueillir les preuves et obtenir les résultats du Judge via le SDK. Aucun changement du statut du registre.

```text
agentbench evaluate [AGENT] [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `-y, --yes` | Ignorer la confirmation d’exécution ; par défaut, elle est demandée. | `--yes` |
| `AGENT` | ID ou numéro d’un Agent activé, facultatif. Sans valeur : sélection interactive ; obligatoire avec --yes. Le statut ready n’est pas requis. | `react-agent` |
| `--registry PATH` | Choisir le registre des Agents ; par défaut : resources/registry.toml du projet. | `--registry resources/registry.toml` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--model MODEL` | Remplacer le modèle cible de substitution ABB ; défaut : configuration du fournisseur choisi. Les modèles ACP natifs suivent la configuration de l’Agent. | `--model openai/gpt-4.1-mini` |
| `--sdk NAME` | Choisir un nom de SDK indiqué par sdk list. Défaut fourni : kuma ; local doit être explicite. Si plusieurs plugins autorisent la sélection implicite, préciser le nom. | `--sdk kuma` |
| `--sdk-options PATH` | Lire un objet JSON d’options du SDK choisi ; défaut : aucune option explicite, valeurs définies par le SDK. | `--sdk-options sdk-options.json` |
| `--case-retries N` | Tentatives automatiques supplémentaires pour un Case récupérable en sécurité. Entier ≥ 0 ; défaut 2, zéro désactive les reprises automatiques. | `--case-retries 0` |
| `--retry-delay SECONDS` | Délai initial avant reprise, en secondes. Nombre fini ≥ 0 ; défaut 5. Les délais suivants augmentent selon la politique. | `--retry-delay 5` |
| `--no-view` | Enregistrer les résultats sans lancer le visualiseur ; par défaut, démarrer ou réutiliser celui-ci. Les ressources web doivent être construites. | `--no-view` |
| `--llm-trace-max-bytes BYTES` | Ancien seuil mémoire du stockage temporaire du flux, en octets ; défaut 262144 (256 Kio). Ne tronque pas les contenus enregistrés. | `--llm-trace-max-bytes 262144` |
| `--results-dir DIR` | Racine des résultats ABB, créée si nécessaire. Depuis la racine du dépôt, défaut : results/. Événements : DIR/suites/SUITE_ID/events.json. Incompatible avec l’ancienne option de destination. | `--results-dir results/my-run` |
| `--result-output PATH` | Ancienne destination ABB : le chemin de fichier choisit son parent sans créer le fichier. Préférer --results-dir, incompatible avec cette option. Défaut : results/ du projet. | `--result-output results/legacy.json` |
| `--output DIR` | Répertoire d’artifacts SDK, distinct des résultats ABB. Remplace output du JSON SDK. Défaut KUMA/local : results/observe. | `--output results/sdk-artifacts` |
| `--timeout SECONDS` | Délai maximal d’exécution SDK, nombre fini positif de secondes. Remplace timeout du JSON SDK. Défaut KUMA/local : 2400 ; les autres SDK définissent le leur. | `--timeout 2400` |
| `--cases N` | Nombre positif de Cases indépendants. Défaut : champ case de l’Agent dans le registre. Le remplacement ne modifie pas le registre. | `--cases 1` |
| `--max-steps N` | Limite SDK positive d’étapes de dialogue par Case. Remplace step du registre et max_steps du JSON SDK ; sinon, conserver leurs défauts. Certains Agents n’acceptent qu’une étape. | `--max-steps 3` |

### Exemples

```bash
agentbench evaluate react-agent --sdk kuma --cases 1
agentbench evaluate react-agent --sdk local --cases 1 --yes --no-view --results-dir results/smoke
agentbench evaluate react-agent --sdk kuma --cases 2 --max-steps 3 --output results/sdk-artifacts --results-dir results/my-run --no-view
```

## `agent add`

Importer un dépôt GitHub ou un répertoire local. Sans -b/-c : import et liste des fichiers. -b génère l’intégration ; -c certifie. Les deux peuvent être combinés.

```text
agentbench agent add SOURCE [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `SOURCE` | URL HTTPS d’un dépôt GitHub ou répertoire local absolu, obligatoire. Pas d’URL de branche/fichier. L’import simple crée une unité ; -b/-c peuvent réutiliser un import correspondant. | `https://github.com/langchain-ai/react-agent` |
| `--agents-dir DIR` | Répertoire parent des unités numérotées ; défaut : resources/agents à côté du registre par défaut du projet. Les unités générées doivent rester dans la racine de --registry. | `--agents-dir resources/agents` |
| `-b, --build` | Générer, valider et enregistrer la configuration puis inscrire adapting. Réutiliser les fichiers valides. LangGraph et ACP sont pris en charge ; aucune construction Docker. Défaut : désactivé. | `-b` |
| `-c, --certify` | Valider l’intégration générée ou manuelle, l’inscrire puis lancer la certification. N’active pas -b implicitement. Défaut : désactivé. | `-c` |
| `--registry PATH` | Choisir le registre des Agents ; par défaut : resources/registry.toml du projet. | `--registry resources/registry.toml` |
| `--build-settings PATH` | Fichier TOML avec une table [build] remplaçant budgets et modèle de génération. Défaut : réglages fournis. Utiliser avec -b. | `--build-settings build-settings.toml` |
| `--build-model MODEL` | Modèle OpenRouter pour la génération -b. Priorité : cette option, [build].model, OPENROUTER_BUILD_MODEL, OPENROUTER_MODEL. Sorties structurées requises. | `--build-model openai/gpt-4.1-mini` |
| `--answers PATH` | Réponses UTF-8 aux questions d’un plan précédent ; répéter -b avec ce fichier. Défaut : aucun fichier de réponses. | `--answers answers.txt` |
| `--with-observe` | Avec -b, générer les champs interactifs pour observe. Défaut : désactivé ; refusé sans -b. | `--with-observe` |
| `--agent-timeout SECONDS` | Avec -b, définir le délai d’exécution de l’Agent généré, en secondes positives finies ; défaut 300. Ce n’est pas le délai de génération. | `--agent-timeout 600` |
| `--adapter-context PATH` | Avec -b, charger un objet JSON explicite de contexte de déploiement, 64 Kio maximum. Défaut : aucun remplacement. Adapter son contenu à l’intégration. | `--adapter-context adapter-context.json` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--model MODEL` | Modèle cible de substitution pour -c, distinct de --build-model. Défaut : configuration du fournisseur ; les modèles ACP natifs suivent l’Agent. | `--model openai/gpt-4.1-mini` |
| `--output PATH` | Destination de certification avec -c. Pour une Suite gérée, un chemin de fichier choisit son parent sans créer le fichier. Défaut : results/ du projet. Pas d’option --results-dir ici. | `--output results/add-certification.json` |
| `--no-view` | Avec -c, enregistrer sans lancer le visualiseur. Aucun effet sur l’import ou la génération. Défaut : visualiseur activé pour la certification. | `--no-view` |
| `-y, --yes` | Ignorer la confirmation de certification -c ; défaut : demander. Ne répond pas aux questions du plan. | `--yes` |
| `--sdk NAME` | Choisir un nom de SDK indiqué par sdk list. Défaut fourni : kuma ; local doit être explicite. Si plusieurs plugins autorisent la sélection implicite, préciser le nom. | `--sdk kuma` |
| `--sdk-options PATH` | Lire un objet JSON d’options SDK pour la certification -c uniquement, pas pour la génération -b. Défaut : valeurs du SDK. | `--sdk-options sdk-options.json` |

Utiliser un chemin local absolu, par exemple "C:\work\local-agent" sous Windows. -d est refusé. La génération utilise OpenRouter et nécessite les interfaces d’intégration SDK, absentes de local.

### Exemples

```bash
agentbench agent add https://github.com/langchain-ai/react-agent
agentbench agent add /absolute/path/to/local-agent -b --sdk kuma --build-model openai/gpt-4.1-mini
agentbench agent add /absolute/path/to/local-agent -b -c --sdk kuma --no-view
```

## `certify`

Exécuter le budget de Cases d’un Agent adapting activé et le promouvoir à ready si tous terminent sans erreur d’invocation. Un constat du Judge ne bloque pas à lui seul la promotion ; pas de nouvelle exécution pour ready.

```text
agentbench certify AGENT_ID [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `-y, --yes` | Ignorer la confirmation d’exécution ; par défaut, elle est demandée. | `--yes` |
| `--registry PATH` | Choisir le registre des Agents ; par défaut : resources/registry.toml du projet. | `--registry resources/registry.toml` |
| `--sdk NAME` | Choisir un nom de SDK indiqué par sdk list. Défaut fourni : kuma ; local doit être explicite. Si plusieurs plugins autorisent la sélection implicite, préciser le nom. | `--sdk kuma` |
| `--sdk-options PATH` | Lire un objet JSON d’options du SDK choisi ; défaut : aucune option explicite, valeurs définies par le SDK. | `--sdk-options sdk-options.json` |
| `--case-retries N` | Tentatives automatiques supplémentaires pour un Case récupérable en sécurité. Entier ≥ 0 ; défaut 2, zéro désactive les reprises automatiques. | `--case-retries 0` |
| `--retry-delay SECONDS` | Délai initial avant reprise, en secondes. Nombre fini ≥ 0 ; défaut 5. Les délais suivants augmentent selon la politique. | `--retry-delay 5` |
| `--no-view` | Enregistrer les résultats sans lancer le visualiseur ; par défaut, démarrer ou réutiliser celui-ci. Les ressources web doivent être construites. | `--no-view` |
| `AGENT_ID` | ID exact obligatoire d’un Agent inscrit et activé. Certifier les Agents adapting ; un Agent ready termine sans nouvelle exécution. | `folder-mover-agent` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--results-dir DIR` | Racine des résultats ABB, créée si nécessaire. Depuis la racine du dépôt, défaut : results/. Événements : DIR/suites/SUITE_ID/events.json. Incompatible avec l’ancienne option de destination. | `--results-dir results/my-run` |
| `--output PATH` | Ancienne destination ABB. Un chemin de fichier choisit son parent sans créer le fichier ; préférer --results-dir. Depuis la racine du dépôt, défaut : results/. | `--output results/legacy.json` |
| `--model MODEL` | Remplacer le modèle cible de substitution ABB ; défaut : configuration du fournisseur choisi. Les modèles ACP natifs suivent la configuration de l’Agent. | `--model openai/gpt-4.1-mini` |
| `--llm-trace-max-bytes BYTES` | Ancien seuil mémoire du stockage temporaire du flux, en octets ; défaut 262144 (256 Kio). Ne tronque pas les contenus enregistrés. | `--llm-trace-max-bytes 262144` |

### Exemples

```bash
agentbench certify AGENT_ID --sdk kuma --no-view
agentbench certify AGENT_ID --sdk local --yes --no-view --results-dir results/certification
```

## `observe`

Exécuter une entrée native et enregistrer sorties et traces, sans génération de Case ni Judge. Requiert actuellement Docker en mode oneshot. --list et --show sont des consultations seules.

```text
agentbench observe [AGENT] [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `AGENT` | ID ou numéro facultatif d’un Agent activé ; sans valeur : sélection interactive. Incompatible avec --agent. | `react-agent` |
| `--agent AGENT` | Autre manière de fournir l’ID ou le numéro ; ne pas combiner avec l’argument positionnel. | `--agent react-agent` |
| `--registry PATH` | Choisir le registre des Agents ; par défaut : resources/registry.toml du projet. | `--registry resources/registry.toml` |
| `--list` | Lister les Agents activés et quitter sans exécution. Défaut : désactivé. | `--list` |
| `--input PATH` | Lire une entrée native JSON UTF-8. Une entrée textuelle est une chaîne JSON avec guillemets. Défaut : saisie interactive des champs observe ou du JSON brut. | `--input native-input.json` |
| `--output DIR` | Racine des artifacts observe ; un sous-répertoire par ID d’exécution est créé. Défaut : results/observe. | `--output results/observe` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--model MODEL` | Remplacer le modèle cible de substitution ABB ; défaut : configuration du fournisseur choisi. Les modèles ACP natifs suivent la configuration de l’Agent. | `--model openai/gpt-4.1-mini` |
| `--timeout SECONDS` | Remplacer le délai d’exécution par un nombre fini positif de secondes ; défaut : configuration d’exécution de l’Agent. | `--timeout 300` |
| `--show DIR` | Consulter hors ligne une exécution observe enregistrée puis quitter ; aucun Agent exécuté, les autres options d’exécution ne sont pas utilisées. | `--show results/observe/RUN_ID` |

### Exemples

```bash
agentbench observe --list
agentbench observe react-agent --input native-input.json --output results/observe --timeout 300
agentbench observe --show results/observe/RUN_ID
```

## `view`

Servir les résultats enregistrés dans le visualiseur local. Construire les ressources web d’abord. Ouvrir l’URL View complète et garder la commande active ; Ctrl+C l’arrête.

```text
agentbench view RESULT_LOG [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `RESULT_LOG` | Fichier JSON de résultat existant obligatoire, normalement events.json indiqué par Result saved. Fournir le fichier, pas son répertoire. | `results/suites/SUITE_ID/events.json` |
| `--host ADDRESS` | Adresse d’écoute du visualiseur ; défaut : 127.0.0.1. | `--host 127.0.0.1` |
| `--port N` | Port d’écoute de 0 à 65535 ; défaut 8765. Zéro demande un port automatique. Le visualiseur peut changer le port par défaut s’il est occupé. | `--port 0` |

### Exemples

```bash
agentbench view results/suites/SUITE_ID/events.json
agentbench view results/suites/SUITE_ID/events.json --host 127.0.0.1 --port 0
```

## `sdk list`

Lister les noms de plugins SDK découverts. Ne vérifie pas que toutes les dépendances d’exécution sont installées.

```text
agentbench sdk list [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |

### Exemples

```bash
agentbench sdk list
```

## `sdk show`

Charger un plugin SDK et afficher sa source, son mode d’exécution et sa sélection implicite.

```text
agentbench sdk show NAME [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `NAME` | Nom obligatoire d’un répertoire SDK, insensible à la casse ; utiliser sdk list. | `kuma` |

### Exemples

```bash
agentbench sdk show kuma
agentbench sdk show local
```

## `resume`

Continuer le travail inachevé récupérable d’une Suite avec Cases et configuration sauvegardés et identifiants actuels. Aucun nouveau Case ni réexécution volontaire des Cases terminés.

```text
agentbench resume SUITE [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `SUITE` | ID, répertoire ou chemin events.json d’une Suite enregistrée, obligatoire. Un ID est résolu dans --suite-root. | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Répertoire contenant les dossiers d’ID de Suite ; défaut : results/suites du répertoire de travail. | `--suite-root results/my-run/suites` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |

### Exemples

```bash
agentbench resume results/suites/SUITE_ID
agentbench resume SUITE_ID --suite-root results/my-run/suites --env-file .env.testing
```

## `retry`

Récupérer un Case inachevé dans sa Suite initiale avec les entrées originales. Selon l’état, reprendre la requête ou rejouer dès la première entrée. Les conditions de rejeu s’appliquent.

```text
agentbench retry SUITE --agent ID --case N [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `SUITE` | ID, répertoire ou chemin events.json d’une Suite enregistrée, obligatoire. Un ID est résolu dans --suite-root. | `results/suites/SUITE_ID` |
| `--suite-root DIR` | Répertoire contenant les dossiers d’ID de Suite ; défaut : results/suites du répertoire de travail. | `--suite-root results/my-run/suites` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--agent ID` | ID exact obligatoire de l’Agent de la Suite initiale, pas un numéro de menu. | `--agent react-agent` |
| `--case N` | Numéro obligatoire de Case, entier positif à partir de 1 ; cible le Case de --agent. | `--case 1` |

### Exemples

```bash
agentbench retry results/suites/SUITE_ID --agent react-agent --case 1
```

## `reuse`

Réutiliser les entrées sauvegardées pour une nouvelle exécution, collecte de preuves et évaluation dans une Suite liée. Conserver les résultats originaux sans nouvelles entrées. Convient aux Cases terminés.

```text
agentbench reuse SOURCE [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `SOURCE` | Suite ID/chemin, Case ID, ID d’artifact, case.json ou chemin de tentative obligatoire. Une Suite choisit tous les Cases sauf avec --agent et --case. Préciser la source d’un ID ambigu. | `CASE_ID` |
| `--suite-root DIR` | Limiter la recherche des Suites à ce répertoire ; défaut : résultats du projet et Suites externes indexées. | `--suite-root results/my-run/suites` |
| `--agent ID` | Avec une source Suite, choisir l’ID exact d’un Agent. Doit accompagner --case. Sans les deux, réexécuter tous les Cases. | `--agent react-agent` |
| `--case N` | Numéro positif de Case à partir de 1 dans une Suite ; accompagner --agent. Ne pas utiliser avec un Case ID direct. | `--case 2` |
| `--output-root DIR` | Répertoire parent des Suites de réexécution. Nouvelle Suite : DIR/SUITE_ID ; défaut : parent de la Suite source. Rejoindre seulement les Suites actives compatibles directement dans ce répertoire. | `--output-root results/reruns` |
| `--env-file PATH` | Charger un autre fichier d’environnement ; défaut : .env du projet. Les variables exportées du shell sont prioritaires. | `--env-file .env.testing` |
| `--model MODEL` | Modèle cible de substitution de la nouvelle évaluation ; défaut : réglages enregistrés. Le modèle ACP natif suit la configuration de l’Agent. | `--model openai/gpt-4.1-mini` |
| `--max-steps N` | Budget SDK positif d’étapes de dialogue pour la nouvelle évaluation ; défaut : réglages enregistrés. N’ajoute pas d’entrées au Case sauvegardé. | `--max-steps 3` |

Les requêtes compatibles peuvent rejoindre une Suite active ; chaque requête volontaire ajoute une exécution. Pas d’options --no-view, --yes, --sdk ou --cases ; un lien de résultat/visualiseur est affiché.

### Exemples

```bash
agentbench reuse CASE_ID
agentbench reuse results/suites/SUITE_ID --agent react-agent --case 2
agentbench reuse results/suites/SUITE_ID --output-root results/reruns --max-steps 3
```

## `clean`

Archiver l’historique non référencé de results du projet dans cache/history-trash. Conserver les Suites et artifacts référencés. Prévisualiser puis arrêter exécutions et visualiseurs avant archivage.

```text
agentbench clean [OPTIONS]
```

| Argument | Rôle et valeur par défaut | Exemple |
| --- | --- | --- |
| `-h, --help` | Afficher l’aide de cette commande et quitter. | `--help` |
| `--dry-run` | Afficher les candidats à l’archivage sans déplacer de fichiers. Défaut : désactivé. | `--dry-run` |
| `-y, --yes` | Ignorer la confirmation d’archivage ; défaut : demander. Arrêter exécutions et visualiseurs avant le nettoyage. | `--yes` |

### Exemples

```bash
agentbench clean --dry-run
agentbench clean
```

## Fichiers utilisés dans les exemples

Créer ces fichiers avant d’utiliser les arguments correspondants. JSON valide obligatoire ; sdk-options.json doit être un objet. Ces options concernent kuma/local ; les autres plugins peuvent utiliser des clés différentes.

`sdk-options.json`:

```json
{
  "timeout": 2400,
  "max_steps": 3
}
```

`build-settings.toml`:

```toml
[build]
model = "openai/gpt-4.1-mini"
timeout_seconds = 120
```

`native-input.json`:

```json
"Describe your capabilities and limitations."
```

native-input.json doit correspondre au schéma natif de l’Agent. answers.txt répond factuellement aux questions du plan. adapter-context.json contient un contexte de déploiement avec -b ; les champs dépendent de l’Agent, sans objet universel à copier.
