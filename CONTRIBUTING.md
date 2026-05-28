# Contributing to ridinCLIgun

- **EN** — English version below.
- **DE** — Die deutsche Version finden Sie weiter unten.
- **FR** — Version française ci-dessous.

---

## English

Thanks for taking a look.

ridinCLIgun is still an early project, maintained by one person, and most of it has been vibe-coded with the help of coding agents and then reviewed again by coding agents (with a certain philosophy on security and quality in mind). That has been useful for building quickly, but it should not be confused with formal review or experienced human verification.

If you want to help, the most valuable contribution right now is professional scrutiny of the security and privacy features.

### What would help most right now

In roughly this order:

1. **Security verification** — check whether the documented protections really hold up in practice
2. **Privacy and data-flow review** — confirm what stays local, what can leave the machine, and where trust boundaries are
3. **Bug reports with reproduction steps** — especially shell, PTY, prompt, paste, and UI edge cases
4. **Small focused fixes** — ideally with tests
5. **Feature ideas** — welcome, but less urgent than verification and correctness

### Especially welcome: security review

If you are experienced in application security, terminal tooling, subprocess handling, or prompt/data sanitization, your review would be especially valuable.

The areas I would most like verified are:

- secret detection and redaction logic
- what is and is not sent to AI providers
- shell and PTY boundary handling
- clipboard and paste-related safety checks
- remote script analysis paths such as `curl | bash`
- places where the docs may currently overstate the actual guarantees

The security model is documented so it can be reviewed, challenged, and improved. It should not be assumed correct just because it is written down.

Relevant docs:

- `docs/security.md`
- `docs/command_analysis.md`

### Before you open a PR

Please keep changes small and easy to review.

- Open an issue first if you want to add a dependency
- Open an issue first if you want to change security controls or data-handling behavior
- Do not include secrets, API keys, or credentials in code, tests, screenshots, logs, or commit messages
- Add tests for bug fixes and for security-relevant changes where practical
- Prefer minimal, explicit changes over broad refactors

### Reporting bugs

Good bug reports are extremely helpful. Please include:

- OS and Python version
- shell and terminal emulator
- exact steps to reproduce
- what you expected to happen
- what actually happened
- any prompt customization that may affect terminal rendering

### Development setup

```bash
# If you want to open a PR, fork the repo on GitHub first.
git clone https://github.com/YOUR_USERNAME/ridinCLIgun.git
cd ridinCLIgun

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pytest tests/ -q
ruff check src/ tests/
```

Requirements:

- Python 3.12+
- a real terminal with PTY support
- macOS for now

For security-relevant changes, it is also worth running:

```bash
bandit -r src/ridincligun/ -c pyproject.toml
pip-audit
```

### Review priorities

When reviewing contributions, I currently care most about:

1. **Security** — no secret leakage, no accidental widening of trust boundaries
2. **Privacy** — local-first behavior should remain the default
3. **User control** — the tool should advise, not take action on the user's behalf
4. **Correctness** — fewer false claims, fewer surprising edge cases
5. **Tests and maintainability** — changes should stay understandable

### Questions

Open an issue or start a [Discussion](https://github.com/inference-garden/ridinCLIgun/discussions).

If response times are slow, that is just the reality of a one-person project.

---

## Deutsch

Vielen Dank für Ihr Interesse.

ridinCLIgun befindet sich noch in einem frühen Stadium, wird von einer Person gepflegt und wurde größtenteils mit Hilfe von Coding Agents programmiert und anschließend erneut von Coding Agents überprüft/auditiert (unter Berücksichtigung einer bestimmten Philosophie in Bezug auf Sicherheit und Qualität). Das war für eine schnelle Entwicklung nützlich, sollte jedoch nicht mit einer formellen Überprüfung oder einer Verifizierung durch erfahrene Fachleute verwechselt werden.

Wenn Sie helfen möchten, ist der derzeit wertvollste Beitrag eine professionelle Überprüfung der Sicherheits- und Datenschutzfunktionen.

### Was derzeit am meisten helfen würde

In etwa dieser Reihenfolge:

1. **Sicherheitsüberprüfung** – prüfen, ob die dokumentierten Schutzmaßnahmen in der Praxis wirklich halten
2. **Überprüfung von Datenschutz und Datenfluss** – bestätigen, was lokal bleibt, was den Rechner verlassen darf und wo die Vertrauensgrenzen liegen
3. **Fehlerberichte mit Reproduktionsschritten** – insbesondere Randfälle bei Shell, PTY, Prompt, Paste und UI
4. **Kleine, gezielte Korrekturen** – idealerweise mit Tests
5. **Feature-Ideen** – willkommen, aber weniger dringend als Überprüfung und Korrektheit

### Besonders willkommen: Sicherheitsüberprüfung

Wenn Sie Erfahrung in den Bereichen Anwendungssicherheit, Terminal-Tools, Subprozess-Handling oder Prompt-/Datenbereinigung haben, wäre Ihre Überprüfung besonders wertvoll.

Die Bereiche, die ich am liebsten überprüft hätte, sind:

- Logik zur Erkennung und Schwärzung geheimer Daten
- Was an KI-Anbieter gesendet wird und was nicht
- Behandlung von Shell- und PTY-Grenzen
- Sicherheitsprüfungen in Bezug auf Zwischenablage und Einfügen
- Pfade zur Analyse von Remote-Skripten wie `curl | bash`
- Stellen, an denen die Dokumentation derzeit die tatsächlichen Garantien möglicherweise überbewertet

Das Sicherheitsmodell ist dokumentiert, damit es überprüft, hinterfragt und verbessert werden kann. Es sollte nicht als korrekt angesehen werden, nur weil es niedergeschrieben ist.

Relevante Dokumente:

- `docs/security.md`
- `docs/command_analysis.md`

### Bevor Sie einen PR eröffnen

Bitte halten Sie Änderungen klein und leicht zu überprüfen.

- Eröffnen Sie zunächst ein Issue, wenn Sie eine Abhängigkeit hinzufügen möchten
- Eröffnen Sie zunächst ein Issue, wenn Sie Sicherheitskontrollen oder das Verhalten bei der Datenverarbeitung ändern möchten
- Fügen Sie keine Geheimnisse, API-Schlüssel oder Anmeldedaten in Code, Tests, Screenshots, Protokolle oder Commit-Meldungen ein
- Fügen Sie Tests für Bugfixes und sicherheitsrelevante Änderungen hinzu, wo dies sinnvoll ist
- Bevorzugen Sie minimale, explizite Änderungen gegenüber umfassenden Refactorings

### Fehler melden

Gute Fehlerberichte sind äußerst hilfreich. Bitte geben Sie Folgendes an:

- Betriebssystem und Python-Version
- Shell und Terminalemulator
- genaue Schritte zur Reproduktion
- was Sie erwartet haben
- was tatsächlich passiert ist
- etwaige Anpassungen der Eingabeaufforderung, die die Darstellung im Terminal beeinflussen könnten

### Entwicklungsumgebung

```bash
# Wenn Sie einen PR eröffnen möchten, forken Sie zuerst das Repo auf GitHub.
git clone https://github.com/YOUR_USERNAME/ridinCLIgun.git
cd ridinCLIgun

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pytest tests/ -q
ruff check src/ tests/
```

Voraussetzungen:

- Python 3.12+
- ein echtes Terminal mit PTY-Unterstützung
- vorerst macOS

Bei sicherheitsrelevanten Änderungen lohnt es sich außerdem, Folgendes auszuführen:

```bash
bandit -r src/ridincligun/ -c pyproject.toml
pip-audit
```

### Prioritäten bei der Überprüfung

Bei der Überprüfung von Beiträgen lege ich derzeit größten Wert auf:

1. **Sicherheit** — keine Offenlegung von Geheimnissen, keine versehentliche Ausweitung von Vertrauensgrenzen
2. **Datenschutz** — Local-first-Verhalten sollte die Standardeinstellung bleiben
3. **Benutzerkontrolle** — das Tool sollte beraten, nicht im Namen des Benutzers handeln
4. **Korrektheit** — weniger falsche Behauptungen, weniger überraschende Randfälle
5. **Tests und Wartbarkeit** — Änderungen sollten verständlich bleiben

### Fragen

Eröffnen Sie ein Issue oder starten Sie eine [Diskussion](https://github.com/inference-garden/ridinCLIgun/discussions).

Sollten die Antwortzeiten lang sein, ist das einfach die Realität eines Ein-Personen-Projekts.

---

## Français

*(Traduction automatique, relue brièvement — les corrections sont les bienvenues.)*

Merci de votre intérêt.

ridinCLIgun est encore un projet naissant, géré par une seule personne, et la majeure partie a été codée de manière intuitive avec l'aide d'agents de codage, puis révisée à nouveau par ces mêmes agents (en gardant à l'esprit une certaine philosophie en matière de sécurité et de qualité). Cela a été utile pour développer rapidement le projet, mais il ne faut pas confondre cela avec une révision formelle ou une vérification humaine par des experts.

Si vous souhaitez apporter votre aide, la contribution la plus précieuse à l'heure actuelle est un examen professionnel des fonctionnalités de sécurité et de confidentialité.

### Ce qui serait le plus utile pour l'instant

Dans l'ordre suivant, approximativement :

1. **Vérification de la sécurité** — vérifier si les protections documentées tiennent vraiment la route dans la pratique
2. **Révision de la confidentialité et des flux de données** — confirmer ce qui reste local, ce qui peut quitter la machine, et où se situent les limites de confiance
3. **Rapports de bogues avec étapes de reproduction** — en particulier les cas limites concernant le shell, le PTY, l'invite de commande, le collage et l'interface utilisateur
4. **Petites corrections ciblées** — idéalement accompagnées de tests
5. **Idées de fonctionnalités** — bienvenues, mais moins urgentes que la vérification et la correction

### Particulièrement bienvenu : examen de sécurité

Si vous avez de l'expérience en sécurité des applications, en outils de terminal, en gestion des sous-processus ou en nettoyage des invites/données, votre examen serait particulièrement précieux.

Les domaines que j'aimerais le plus voir vérifiés sont :

- la logique de détection et de masquage des secrets
- ce qui est et n'est pas envoyé aux fournisseurs d'IA
- la gestion des limites du shell et du PTY
- les contrôles de sécurité liés au presse-papiers et au collage
- les chemins d'analyse de scripts à distance tels que `curl | bash`
- les endroits où la documentation pourrait actuellement surestimer les garanties réelles

Le modèle de sécurité est documenté afin de pouvoir être examiné, remis en question et amélioré. Il ne faut pas le considérer comme correct simplement parce qu'il est écrit.

Documents pertinents :

- `docs/security.md`
- `docs/command_analysis.md`

### Avant d'ouvrir une PR

Veuillez limiter les modifications à des changements mineurs et faciles à examiner.

- Ouvrez d'abord un ticket si vous souhaitez ajouter une dépendance
- Ouvrez d'abord un ticket si vous souhaitez modifier les contrôles de sécurité ou le comportement de traitement des données
- N'incluez pas de secrets, de clés API ou d'identifiants dans le code, les tests, les captures d'écran, les journaux ou les messages de commit
- Ajoutez des tests pour les corrections de bogues et pour les modifications liées à la sécurité lorsque cela est possible
- Privilégiez les modifications minimales et explicites plutôt que les refactorisations à grande échelle

### Signalement des bogues

Les bons rapports de bogues sont extrêmement utiles. Veuillez inclure :

- le système d'exploitation et la version de Python
- le shell et l'émulateur de terminal
- les étapes exactes pour reproduire le bogue
- ce que vous vous attendiez à voir se produire
- ce qui s'est réellement produit
- toute personnalisation de l'invite de commande susceptible d'affecter l'affichage du terminal

### Configuration de développement

```bash
# Si vous souhaitez ouvrir une pull request, commencez par créer une branche du dépôt sur GitHub.
git clone https://github.com/YOUR_USERNAME/ridinCLIgun.git
cd ridinCLIgun

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"

pytest tests/ -q
ruff check src/ tests/
```

Configuration requise :

- Python 3.12+
- un véritable terminal prenant en charge PTY
- macOS pour l'instant

Pour les modifications liées à la sécurité, il est également recommandé d'exécuter :

```bash
bandit -r src/ridincligun/ -c pyproject.toml
pip-audit
```

### Priorités de révision

Lors de la révision des contributions, je privilégie actuellement les aspects suivants :

1. **Sécurité** — aucune fuite d'informations confidentielles, aucun élargissement accidentel des limites de confiance
2. **Confidentialité** — le comportement local-first doit rester la valeur par défaut
3. **Contrôle par l'utilisateur** — l'outil doit conseiller, et non agir au nom de l'utilisateur
4. **Exactitude** — moins de fausses affirmations, moins de cas limites surprenants
5. **Tests et maintenabilité** — les modifications doivent rester compréhensibles

### Questions

Ouvrez un ticket ou lancez une [discussion](https://github.com/inference-garden/ridinCLIgun/discussions).

Si les délais de réponse sont longs, c'est simplement la réalité d'un projet mené par une seule personne.
