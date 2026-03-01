#!/usr/bin/env python3
"""Fetch anti-cheat data from AreWeAntiCheatYet.

Downloads the games.json from the GitHub repo and matches entries
to existing games by name or Steam app_id.

Usage:
    python fetch_anticheat.py                          # Standalone
    from fetch_anticheat import fetch; fetch(db_path)  # As module
"""

import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ANTICHEAT_URL = (
    "https://raw.githubusercontent.com/AreWeAntiCheatYet/"
    "AreWeAntiCheatYet/HEAD/games.json"
)

# Timeout for the HTTP request (seconds).
REQUEST_TIMEOUT = 30

# Map AreWeAntiCheatYet status -> our simplified status.
STATUS_MAP = {
    "Supported": "supported",
    "Running": "running",
    "Planned": "planned",
    "Broken": "broken",
    "Denied": "denied",
}


def _build_name_index(cur: sqlite3.Cursor) -> dict[str, int]:
    """Build a lowercase name -> app_id index from existing games."""
    cur.execute("SELECT app_id, name FROM games")
    index: dict[str, int] = {}
    for app_id, name in cur.fetchall():
        key = name.strip().lower()
        # Prefer real (positive) app_ids over placeholders.
        if key not in index or app_id > 0:
            index[key] = app_id
    return index


def _find_app_id(
    cur: sqlite3.Cursor,
    name_index: dict[str, int],
    entry: dict,
) -> int | None:
    """Try to match an AreWeAntiCheatYet entry to a game in our DB.

    Matching priority:
    1. Steam appid from storeIds.
    2. Exact name match (case-insensitive).
    """
    # Try Steam appid first.
    store_ids = entry.get("storeIds", {})
    steam_id = store_ids.get("steam")
    if steam_id:
        try:
            steam_id_int = int(steam_id)
            cur.execute("SELECT app_id FROM games WHERE app_id = ?", (steam_id_int,))
            if cur.fetchone():
                return steam_id_int
        except (ValueError, TypeError):
            pass

    # Fallback: name match.
    name = entry.get("name", "").strip().lower()
    if name and name in name_index:
        return name_index[name]

    return None


def fetch(db_path: Path) -> int:
    """Fetch anti-cheat data and update linux_compat.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of entries matched and updated.
    """
    logger.info("Fetching AreWeAntiCheatYet data from %s", ANTICHEAT_URL)

    try:
        resp = requests.get(ANTICHEAT_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch anti-cheat data: %s", exc)
        return 0

    try:
        entries = resp.json()
    except ValueError as exc:
        logger.error("Failed to parse anti-cheat JSON: %s", exc)
        return 0

    if not isinstance(entries, list):
        logger.error("Expected JSON array, got %s", type(entries).__name__)
        return 0

    logger.info("AreWeAntiCheatYet: %d total entries", len(entries))

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    name_index = _build_name_index(cur)

    matched = 0
    unmatched = 0

    for entry in entries:
        name = entry.get("name", "").strip()
        if not name:
            continue

        app_id = _find_app_id(cur, name_index, entry)
        if app_id is None:
            unmatched += 1
            continue

        # Extract anti-cheat info.
        anticheats = entry.get("anticheats", [])
        anticheat_str = ", ".join(anticheats) if anticheats else None

        status_raw = entry.get("status", "")
        anticheat_linux = STATUS_MAP.get(status_raw, status_raw.lower() if status_raw else None)

        # Upsert into linux_compat.
        cur.execute(
            """INSERT INTO linux_compat (app_id, anticheat, anticheat_linux)
               VALUES (?, ?, ?)
               ON CONFLICT(app_id) DO UPDATE SET
                   anticheat = COALESCE(excluded.anticheat, linux_compat.anticheat),
                   anticheat_linux = COALESCE(excluded.anticheat_linux, linux_compat.anticheat_linux)
            """,
            (app_id, anticheat_str, anticheat_linux),
        )
        matched += 1

    # Record source metadata.
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT OR REPLACE INTO data_sources
               (source_id, last_updated, entries_count, url, notes)
           VALUES ('anticheat', ?, ?, ?, 'AreWeAntiCheatYet')""",
        (now, matched, ANTICHEAT_URL),
    )

    conn.commit()
    conn.close()
    logger.info(
        "Anti-cheat fetch complete: %d matched, %d unmatched out of %d total",
        matched, unmatched, len(entries),
    )
    return matched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    db = Path(__file__).parent.parent / "data" / "linuxplaydb.db"
    if not db.exists():
        print(f"ERROR: Database not found at {db}", file=sys.stderr)
        sys.exit(1)
    count = fetch(db)
    print(f"Matched {count} anti-cheat entries")
