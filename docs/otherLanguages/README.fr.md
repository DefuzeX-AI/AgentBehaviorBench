# AgentBehaviorBench (ABB)

<p align="center">
  <img
    alt="AgentBehaviorBench — évaluation du comportement des Agents"
    src="../figures/title.png"
    width="720"
    style="border-radius: 24px;"
  >
</p>

<p align="center">
  <a href="../../README.md">English</a> |
  Français |
  <a href="README.ja.md">日本語</a> |
  <a href="README.zh-CN.md">中文</a> |
  <a href="README.ko.md">한국어</a>
</p>

<p align="center">
  <img alt="Python 3.10 ou version ultérieure" src="https://img.shields.io/badge/Python-3.10%2B-8a008a">
  <img alt="Licence MIT" src="https://img.shields.io/badge/License-MIT-0086c9">
  <img alt="Version du package 0.1.0" src="https://img.shields.io/badge/pypi%20package-0.1.0-2acb16">
</p>

## Qu’est-ce qu’ABB ?

AgentBehaviorBench (ABB) est un benchmark qui évalue la capacité des Agents IA à
tester le comportement d’autres Agents. Il comprend deux jeux de données : des
Agents cibles directement exécutables et des défauts comportementaux confirmés
par des tests manuels, qui constituent la vérité de référence (Ground Truth).
Un Agent de test participant au benchmark génère des cas de test, les fait
exécuter par l’Agent cible et analyse les trajectoires d’exécution obtenues pour
identifier les problèmes de cet Agent.

## Vue d’ensemble

ABB intègre des Agents cibles construits avec différents frameworks au moyen
d’Adapters et utilise un pipeline commun pour exécuter les cas de test et collecter
les preuves comportementales. Un Agent de test intégré à ABB doit pouvoir générer
des cas de test, analyser les preuves d’exécution et déterminer les défauts
comportementaux (Judge), et se connecte via un SDK d’évaluation. Les preuves
comprennent les entrées de test, les sorties de l’Agent et son état d’exécution,
les traces OpenTelemetry, ainsi que les changements de fichiers et les diffs
lorsque la collecte des preuves de fichiers est activée. L’Agent de test doit
signaler les défauts comportementaux à partir de ces preuves ; dans le benchmark,
l’identification d’un défaut spécifié dans la Ground Truth rapporte les points
correspondants.

Chaque Agent de test participant à AgentBehaviorBench doit disposer des capacités suivantes :

1. **Génération de cas de test (Case Generation)** : Générer des cas de test qui examinent le comportement de l’Agent cible à partir de ses capacités et de ses contraintes comportementales.
2. **Analyse des trajectoires (Trajectory Analysis)** : Analyser les entrées de test, les sorties de l’Agent, les traces OpenTelemetry et les preuves de changements de fichiers afin d’identifier des anomalies comportementales potentielles.
3. **Détermination des défauts (Judging)** : Déterminer, à partir des preuves d’exécution, si l’Agent cible présente des défauts comportementaux et signaler les problèmes précis avec les preuves qui les étayent.

![Architecture AgentBehaviorBench](../figures/abb-suite-sdk-roles.png)

Le registre indique la révision du code source testée et la manière dont ABB doit
lancer l’Agent. Le harness planifie les Cases, démarre les conteneurs, exécute
l’Agent Run, route les communications déclarées et collecte les traces et preuves
du système de fichiers. L’état d’exécution et le verdict du Judge restent distincts :
un Agent peut s’exécuter correctement tout en présentant un problème comportemental.

## Ressources

- [Agents intégrés](Agents.fr.md) — Agents cibles, dépôts sources et révisions sélectionnées.
- [Comprendre le registre des Agents](Registry.fr.md) — Champs de `registry.toml`, sélection des Agents et budgets de Cases.
- [Ajouter un Agent](How%20To%20Add%20Agent.fr.md)
- [Référence CLI](cli.fr.md)
- [Démarrer ABB — anglais](../Guide.md)

## SDK d’évaluation et Judge

Les évaluations officielles utilisent actuellement le
[SDK KUMA DefuzeX](https://github.com/DefuzeX-AI/KUMA-DefuzeX), installé via
`kuma-defuzex[otel]`. L’installation du SDK sélectionne la dernière version stable
sur PyPI. Les images et couches Docker existantes sont réutilisées et ne sont pas
actualisées automatiquement à chaque nouvelle version du SDK. KUMA génère les Cases comportementaux, reçoit les
preuves collectées par ABB et les transmet au Judge DefuzeX. Le verdict et son
évaluation sont enregistrés avec les artifacts de la Suite.

ABB inclut également un plugin SDK `local` avec des Cases de contrôle fixes et un
Judge local. Aucun crédit backend KUMA n’est requis, mais les appels modèle de
l’Agent et du Judge peuvent être payants. Ce plugin n’est pas le Judge officiel des benchmarks.


## Documentation complémentaire

- [Résultats et dépannage — anglais](../Troubleshooting.md)

## Licence

MIT. Voir [LICENSE](../../LICENSE).
