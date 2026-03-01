# LinuxPlayDB

## Project Overview
Database of Steam games with Ray Tracing/Path Tracing compatibility info, AMD status, Linux/Proton commands, and handheld device support. Static site served via GitHub Pages using sql.js (SQLite in WASM).

## Architecture
- **Backend scripts**: Python 3.12+ — fetch data from NVIDIA, Steam, ProtonDB, etc.
- **Frontend**: Vanilla HTML/CSS/JS — no frameworks, sql.js for WASM SQLite queries
- **Database**: SQLite (`data/linuxplaydb.db`) served as static file, loaded by sql.js in browser
- **i18n**: ES/EN with `lang/*.json` files and `notes_en`/`notes_es` columns in DB

## Key Paths
- `scripts/build_db.py` — Main orchestrator: combines all data sources into SQLite
- `scripts/migrate_seed.py` — Migrates original HTML data (~210 games) to SQLite
- `scripts/fetch_*.py` — Individual data source fetchers
- `scripts/manual/*.json` — Hand-curated data (AMD, Linux commands, handhelds)
- `site/` — Static frontend served by GitHub Pages
- `site/js/db.js` — sql.js wrapper, all DB queries go through here
- `data/seed/all_steam_rt_games.html` — Original seed data (reference only)

## Code Standards
- Python: snake_case, type hints, docstrings on public functions
- JavaScript: camelCase, no framework dependencies, ES2020+
- CSS: BEM-like naming with `lpdb-` prefix
- Comments in English

## Git Workflow
- Commits: English, Conventional Commits (`feat:`, `fix:`, `docs:`)
- No AI signatures in commits or PRs
- Branch flow: `main` (releases) ← `development` (integration) ← `feat/*`

## Build Commands
```bash
# Install Python deps
pip install -r scripts/requirements.txt

# Build database from all sources
python scripts/build_db.py

# Migrate seed data only
python scripts/migrate_seed.py

# Serve site locally
python -m http.server 8080 --directory site
```

## Database Schema
See `scripts/build_db.py` for full schema. Key tables:
- `games` — Core game info (~70K potential entries)
- `graphics_features` — RT/PT, DLSS, FSR support
- `linux_compat` — Proton, Deck status, launch commands
- `devices` — Handhelds and GPUs (~40+ entries)
- `device_compat` — Per-game per-device compatibility
- `useful_links` — External resources per game
- `data_sources` — Metadata about data freshness

## Data Sources
- NVIDIA RTX DB (auto): `dlss-rt-games-apps-overrides.json`
- Steam Store API (auto): app details, Deck compat
- ProtonDB (auto): tier summaries
- AreWeAntiCheatYet (auto): anti-cheat status
- Manual: AMD quirks, Linux commands, handheld compat
