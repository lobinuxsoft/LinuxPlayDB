# Contributing to LinuxPlayDB

Thank you for your interest in contributing! This document outlines our development workflow and standards.

## Quick Reference

| Item | Value |
|------|-------|
| PRs target | `development` branch |
| Commit language | English |
| Commit format | [Conventional Commits](https://www.conventionalcommits.org/) |
| Code comments | English |

## Issue-First Development

**Always create an issue before coding.**

```
Create Issue → Create Branch → Develop → PR to development → Close Issue
```

This ensures work is tracked, discussed, and properly scoped before implementation begins.

## Branch Naming

Create branches from issues using this pattern:

```
feature/issue-XX-short-description
fix/issue-XX-short-description
docs/issue-XX-short-description
refactor/issue-XX-short-description
```

Example: `feature/issue-10-add-deck-filter`

## Commit Messages

Write commits in **English** using Conventional Commits format:

```
feat: add handheld device filter
fix: fix search debounce on mobile
docs: update data sources table
refactor: simplify SQL query builder
test: add migration tests
chore: update dependencies
```

### Types

| Type | Use for |
|------|---------|
| `feat` | New features |
| `fix` | Bug fixes |
| `docs` | Documentation only |
| `refactor` | Code changes that neither fix bugs nor add features |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks |
| `build` | Build system changes |

## Pull Requests

1. **Target branch**: `development`
2. **Title**: Clear description of the change
3. **Body**: Reference the issue with `Closes #XX`
4. **Size**: Keep PRs focused and reviewable

```bash
# Example PR creation
gh pr create --base development --title "feat: add handheld device filter" --body "Closes #10"
```

## Code Standards

### Python (Data Pipeline)

| Item | Convention |
|------|------------|
| Files | `snake_case.py` |
| Functions/Variables | `snake_case` |
| Classes | `PascalCase` |
| Comments | English |
| Type hints | Recommended |

### JavaScript (Frontend)

| Item | Convention |
|------|------------|
| Files | `camelCase.js` |
| Variables/Functions | `camelCase` |
| Constants | `UPPER_SNAKE_CASE` |
| CSS classes | `lpdb-` prefix, BEM-like |
| Comments | English |

### General Guidelines

- **Comments**: Write in English
- **Error handling**: Wrap errors with context
- **Security**: Never commit API keys or credentials

## Building the Project

```bash
# Install Python dependencies
pip install -r scripts/requirements.txt

# Build database (seed + manual data)
python scripts/build_db.py

# Build database with online fetch
python scripts/build_db.py --fetch

# Serve site locally
python -m http.server 8080 --directory site
```

## Contributing Data

The most impactful contributions are **game data**. Use the research prompts in `scripts/prompts/` to structure your research:

1. **AMD compatibility**: Test RT/PT on AMD GPUs, document workarounds
2. **Linux commands**: Find launch options, env vars, Proton versions
3. **Handheld testing**: Report FPS, settings, TDP for device + game combos
4. **Useful links**: ProtonDB reports, PCGamingWiki pages, Reddit fixes

Add curated data to the appropriate JSON in `scripts/manual/`.

## Labels

When creating issues, use appropriate labels:

| Category | Labels |
|----------|--------|
| Priority | `priority:critical`, `priority:high`, `priority:medium`, `priority:low` |
| Difficulty | `difficulty:easy`, `difficulty:medium`, `difficulty:hard` |
| Component | `frontend`, `data-pipeline`, `database`, `i18n`, `handhelds` |

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/lobinuxsoft/LinuxPlayDB/discussions)
- **Bugs**: Create an [Issue](https://github.com/lobinuxsoft/LinuxPlayDB/issues)

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
