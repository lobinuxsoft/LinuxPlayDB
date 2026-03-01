# LinuxPlayDB

Database of Steam games with Ray Tracing / Path Tracing compatibility, AMD & NVIDIA support status, Linux/Proton commands, and handheld device compatibility.

[**Leer en Español**](README.es.md)

## Features

- **RT/PT Database**: ~200+ games with Ray Tracing and Path Tracing support data
- **AMD Compatibility**: Status for each game — works, RT-only, or NVIDIA-exclusive
- **Linux Commands**: Steam launch options, environment variables, Proton versions
- **Handheld Support**: 40+ devices tracked (Steam Deck, ROG Ally, Legion Go, etc.)
- **Bazzite Reference**: Quick reference for RT on Bazzite Linux (RADV + Mesa 26)
- **Offline-First**: SQLite database runs entirely in the browser via WASM
- **i18n**: Available in English and Spanish
- **Export**: CSV and JSON export of filtered data
- **Auto-Update**: Weekly data refresh via GitHub Actions

## Tech Stack

- **Frontend**: Vanilla HTML/CSS/JS — no frameworks
- **Database**: SQLite via [sql.js](https://github.com/sql-js/sql.js/) (WASM)
- **Data Pipeline**: Python scripts for fetching from NVIDIA, Steam, ProtonDB
- **Hosting**: GitHub Pages (free)
- **CI/CD**: GitHub Actions for automated weekly updates

## Quick Start

### View the site

Visit the live site at GitHub Pages (link TBD after deployment).

### Run locally

```bash
# Clone
git clone https://github.com/YOUR_USERNAME/LinuxPlayDB.git
cd LinuxPlayDB

# Install Python dependencies
pip install -r scripts/requirements.txt

# Build the database
python scripts/build_db.py

# Serve locally
python -m http.server 8080 --directory site
# Open http://localhost:8080
```

### Rebuild with online data

```bash
python scripts/build_db.py --fetch
```

## Data Sources

| Source | Type | Data |
|--------|------|------|
| [NVIDIA RTX DB](https://www.nvidia.com/en-us/geforce/news/nvidia-rtx-games-engines-apps/) | Auto | RT/PT, DLSS, Ray Reconstruction |
| [Steam Store API](https://store.steampowered.com/) | Auto | Game details, genres, images |
| [ProtonDB](https://www.protondb.com/) | Auto | Linux compatibility tiers |
| [Steam Deck Compat](https://store.steampowered.com/) | Auto | Verified/Playable/Unsupported |
| [AreWeAntiCheatYet](https://areweanticheatyet.com/) | Auto | Anti-cheat Linux status |
| Manual Research | Manual | AMD quirks, Linux commands, handheld data |

## Project Structure

```
LinuxPlayDB/
├── data/seed/          # Original HTML seed data
├── scripts/            # Python data pipeline
│   ├── fetch_*.py      # Auto-fetch from online sources
│   ├── build_db.py     # Database builder (orchestrator)
│   ├── migrate_seed.py # HTML -> SQLite migration
│   ├── manual/         # Hand-curated JSON data
│   └── prompts/        # AI research prompt templates
├── site/               # Static frontend
│   ├── css/style.css   # Dark theme (cyan/orange)
│   ├── js/             # App modules
│   ├── lang/           # i18n translations
│   └── lib/            # sql.js WASM
└── .github/workflows/  # CI/CD
```

## Contributing

Contributions welcome! Areas where help is most needed:

1. **Game Data**: Research AMD compatibility, Linux commands, and Proton versions
2. **Handheld Testing**: Report FPS, settings, and TDP data for specific device + game combos
3. **Translations**: Improve Spanish/English content in the database
4. **Bug Reports**: Issues with the site or data accuracy

Use the prompt templates in `scripts/prompts/` for structured game research.

## License

[MIT](LICENSE)
