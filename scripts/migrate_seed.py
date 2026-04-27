#!/usr/bin/env python3
"""Migrate game data from the original HTML seed file into SQLite.

Parses the embedded GAMES_DB JavaScript array from all_steam_rt_games.html
and inserts records into the games, graphics_features, and linux_compat tables.
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

SEED_FILE = Path(__file__).parent.parent / "data" / "seed" / "all_steam_rt_games.html"
DB_FILE = Path(__file__).parent.parent / "data" / "linuxplaydb.db"

# Maps for seed data fields -> DB columns
AMD_STATUS_MAP = {
    "amd_ok": "amd_ok",
    "pt_too": "amd_pt",
    "amd_rt_only": "amd_rt_only",
    "nvidia_pt": "nvidia_only",
}

LINUX_STATUS_MAP = {
    "works": "works",
    "cmd": "cmd",
    "broken": "broken",
    "check": "check",
}


def extract_games_array(html: str) -> list[dict]:
    """Extract the GAMES_DB array from the HTML source."""
    match = re.search(r"const GAMES_DB\s*=\s*\[(.+?)\];", html, re.DOTALL)
    if not match:
        print("ERROR: Could not find GAMES_DB array in HTML")
        sys.exit(1)

    raw = match.group(1)

    # Remove single-line comments
    raw = re.sub(r"//[^\n]*", "", raw)

    # Extract string literals first, replace with placeholders to avoid
    # modifying content inside strings (e.g. WineDetectionEnabled:False)
    strings_store = []

    def store_string(m):
        strings_store.append(m.group(0))
        return f'"__STR_{len(strings_store) - 1}__"'

    raw = re.sub(r'"(?:[^"\\]|\\.)*"', store_string, raw)

    # Now safely quote unquoted JS keys (only bare identifiers before colons)
    raw = re.sub(r'(\w+)\s*:', r'"\1":', raw)

    # JS booleans (true/false) are already valid JSON — no conversion needed
    # Remove trailing commas (valid in JS, invalid in JSON)
    raw = re.sub(r",\s*(?=[}\]])", "", raw)
    raw = raw.rstrip().rstrip(",")

    # Restore original strings
    def restore_string(m):
        idx = int(m.group(1))
        return strings_store[idx]

    raw = re.sub(r'"__STR_(\d+)__"', restore_string, raw)

    try:
        games = json.loads(f"[{raw}]")
    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to parse GAMES_DB: {e}")
        sys.exit(1)

    return games


def parse_env_vars(cmd: str) -> dict:
    """Extract environment variables from a launch command string."""
    env_vars = {}
    # Match KEY=VALUE patterns before %command%
    parts = cmd.split("%command%")[0] if "%command%" in cmd else ""
    for match in re.finditer(r"(\w+)=(\S+)", parts):
        key, val = match.groups()
        if key not in ("command",):
            env_vars[key] = val
    return env_vars


def migrate(db_path: Path = DB_FILE) -> int:
    """Run the migration. Returns number of games migrated."""
    if not SEED_FILE.exists():
        print(f"ERROR: Seed file not found: {SEED_FILE}")
        sys.exit(1)

    html = SEED_FILE.read_text(encoding="utf-8")
    games = extract_games_array(html)
    print(f"Parsed {len(games)} games from seed HTML")

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    migrated = 0
    for g in games:
        name = g.get("name", "").strip()
        if not name:
            continue

        # Use a negative app_id as placeholder (real IDs come from Steam API)
        # We'll use a hash of the name to get a stable negative ID
        app_id = -(abs(hash(name)) % 900000 + 100000)

        # Check if already exists (by name, since we don't have real app_ids)
        cur.execute("SELECT app_id FROM games WHERE name = ?", (name,))
        existing = cur.fetchone()
        if existing:
            app_id = existing[0]
        else:
            # Insert into games table
            cur.execute(
                """INSERT OR IGNORE INTO games (app_id, name, type, steam_url)
                   VALUES (?, ?, 'game', ?)""",
                (app_id, name, f"https://store.steampowered.com/search/?term={name.replace(' ', '+')}")
            )

        # Graphics features
        rt_type = "pt" if g.get("pt") else "rt"
        amd_status = AMD_STATUS_MAP.get(g.get("amdStatus", ""), g.get("amdStatus", ""))
        notes = g.get("linuxNotes", "")

        cur.execute(
            """INSERT OR REPLACE INTO graphics_features
               (app_id, rt_type, dlss_sr, dlss_fg, dlss_rr, dlss_mfg, dlaa, fsr4, fsr3, fsr2, xess,
                amd_status, notes_en, notes_es)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, ?, ?, ?)""",
            (
                app_id, rt_type,
                int(g.get("sr", False)),
                int(g.get("fg", False)),
                int(g.get("rr", False)),
                int(g.get("mfg", False)),
                int(g.get("dlaa", False)),
                int(g.get("fsr4", False)),
                amd_status,
                notes,
                notes,  # Same text for both languages in seed data
            )
        )

        # Linux compat
        linux_status = LINUX_STATUS_MAP.get(g.get("linuxStatus", ""), g.get("linuxStatus", ""))
        linux_cmd = g.get("linuxCmd", "")
        proton = g.get("proton", "")
        env_vars = parse_env_vars(linux_cmd) if linux_cmd else {}

        # Determine launch options vs env vars
        launch_options = linux_cmd
        native = 1 if proton and "nativo" in proton.lower() else 0

        cur.execute(
            """INSERT OR REPLACE INTO linux_compat
               (app_id, native_linux, proton_version, linux_status, launch_options, env_vars,
                notes_en, notes_es)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                app_id, native,
                proton if proton else None,
                linux_status,
                launch_options if launch_options else None,
                json.dumps(env_vars) if env_vars else None,
                notes,
                notes,
            )
        )

        migrated += 1

    conn.commit()
    conn.close()
    print(f"Migrated {migrated} games to {db_path}")
    return migrated


if __name__ == "__main__":
    migrate()
