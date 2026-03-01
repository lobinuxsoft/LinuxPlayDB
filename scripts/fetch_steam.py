#!/usr/bin/env python3
"""Fetch game data from the Steam Store API.

Two-phase approach:
1. Get the full app list to map names -> app_ids.
2. Fetch detailed info for games already in the DB that need enrichment.

Rate limit: ~200 requests per 5 minutes (throttled to ~1.5s between requests).

Usage:
    python fetch_steam.py                     # Standalone
    from fetch_steam import fetch; fetch(db_path)  # As module
"""

import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

STEAM_APP_LIST_URL = "https://api.steampowered.com/ISteamApps/GetAppList/v2/"
STEAM_APP_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

# ~200 requests per 5 min = 1 per 1.5s.
RATE_LIMIT_SECONDS = 1.5

# Timeout per request (seconds).
REQUEST_TIMEOUT = 15

# How many detail requests to make per run (safety cap).
MAX_DETAIL_REQUESTS = 500


def _fetch_app_list(session: requests.Session) -> dict[str, int]:
    """Fetch the full Steam app list. Returns {lowercase_name: appid}."""
    logger.info("Fetching Steam app list...")
    try:
        resp = session.get(STEAM_APP_LIST_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch Steam app list: %s", exc)
        return {}

    data = resp.json()
    apps = data.get("applist", {}).get("apps", [])
    logger.info("Steam app list: %d entries", len(apps))

    # Build lookup: lowercase name -> appid (prefer lower appids for duplicates).
    lookup: dict[str, int] = {}
    for app in apps:
        name = app.get("name", "").strip()
        appid = app.get("appid")
        if not name or not appid:
            continue
        key = name.lower()
        if key not in lookup or appid < lookup[key]:
            lookup[key] = appid
    return lookup


def _resolve_app_ids(cur: sqlite3.Cursor, steam_lookup: dict[str, int]) -> int:
    """Resolve negative placeholder app_ids to real Steam app_ids.

    Returns the number of games resolved.
    """
    cur.execute("SELECT app_id, name FROM games WHERE app_id < 0")
    unresolved = cur.fetchall()
    if not unresolved:
        return 0

    resolved = 0
    for old_id, name in unresolved:
        key = name.strip().lower()
        real_id = steam_lookup.get(key)
        if real_id is None:
            continue

        # Check if the real_id already exists (avoid PK conflict).
        cur.execute("SELECT 1 FROM games WHERE app_id = ?", (real_id,))
        if cur.fetchone():
            # Merge: keep the existing real entry, delete the placeholder.
            cur.execute("DELETE FROM graphics_features WHERE app_id = ?", (old_id,))
            cur.execute("DELETE FROM linux_compat WHERE app_id = ?", (old_id,))
            cur.execute("DELETE FROM games WHERE app_id = ?", (old_id,))
            continue

        # Swap the placeholder ID for the real one across all tables.
        cur.execute("UPDATE games SET app_id = ? WHERE app_id = ?", (real_id, old_id))
        cur.execute("UPDATE graphics_features SET app_id = ? WHERE app_id = ?", (real_id, old_id))
        cur.execute("UPDATE linux_compat SET app_id = ? WHERE app_id = ?", (real_id, old_id))
        cur.execute("UPDATE device_compat SET app_id = ? WHERE app_id = ?", (real_id, old_id))
        cur.execute("UPDATE useful_links SET app_id = ? WHERE app_id = ?", (real_id, old_id))
        resolved += 1

    logger.info("Resolved %d/%d placeholder app_ids", resolved, len(unresolved))
    return resolved


def _fetch_app_details(session: requests.Session, app_id: int) -> dict | None:
    """Fetch details for a single app. Returns parsed data dict or None."""
    try:
        resp = session.get(
            STEAM_APP_DETAILS_URL,
            params={"appids": str(app_id)},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 429:
            logger.warning("Rate limited on app %d, backing off 30s", app_id)
            time.sleep(30)
            return None
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("App %d: request failed: %s", app_id, exc)
        return None

    try:
        payload = resp.json()
    except ValueError:
        logger.warning("App %d: invalid JSON response", app_id)
        return None

    app_data = payload.get(str(app_id), {})
    if not app_data.get("success"):
        return None

    return app_data.get("data", {})


def _enrich_game(cur: sqlite3.Cursor, app_id: int, data: dict) -> None:
    """Update a game row with enriched Steam data."""
    name = data.get("name", "").strip()
    genres_list = data.get("genres", [])
    genres = ", ".join(g.get("description", "") for g in genres_list) if genres_list else None

    release = data.get("release_date", {})
    release_date = release.get("date") if not release.get("coming_soon") else None

    header_image = data.get("header_image")
    steam_url = f"https://store.steampowered.com/app/{app_id}/"

    # Detect Linux native support.
    platforms = data.get("platforms", {})
    native_linux = platforms.get("linux", False)

    cur.execute(
        """UPDATE games SET
               name = COALESCE(?, name),
               release_date = COALESCE(?, release_date),
               genres = COALESCE(?, genres),
               steam_url = ?,
               header_image = COALESCE(?, header_image)
           WHERE app_id = ?""",
        (name or None, release_date, genres, steam_url, header_image, app_id),
    )

    # Update native Linux flag if detected.
    if native_linux:
        cur.execute(
            """INSERT INTO linux_compat (app_id, native_linux)
               VALUES (?, 1)
               ON CONFLICT(app_id) DO UPDATE SET native_linux = 1""",
            (app_id,),
        )


def fetch(db_path: Path) -> int:
    """Fetch Steam data: resolve app_ids, then enrich game details.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of games enriched with details.
    """
    session = requests.Session()
    session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Phase 1: Resolve placeholder IDs.
    steam_lookup = _fetch_app_list(session)
    if steam_lookup:
        resolved = _resolve_app_ids(cur, steam_lookup)
        conn.commit()
        logger.info("Phase 1 complete: %d IDs resolved", resolved)
    else:
        logger.warning("Steam app list unavailable — skipping ID resolution")

    # Phase 2: Enrich games that lack details.
    cur.execute(
        """SELECT app_id FROM games
           WHERE app_id > 0
             AND (header_image IS NULL OR genres IS NULL OR release_date IS NULL)
           ORDER BY app_id
           LIMIT ?""",
        (MAX_DETAIL_REQUESTS,),
    )
    to_enrich = [row[0] for row in cur.fetchall()]

    if not to_enrich:
        logger.info("No games need enrichment")
        conn.close()
        return 0

    logger.info("Enriching %d games from Steam Store API (rate: ~1.5s/req)", len(to_enrich))

    enriched = 0
    for i, app_id in enumerate(to_enrich):
        data = _fetch_app_details(session, app_id)
        if data:
            _enrich_game(cur, app_id, data)
            enriched += 1

        # Progress + intermediate commit every 25 games.
        if (i + 1) % 25 == 0:
            logger.info("Progress: %d/%d (enriched: %d)", i + 1, len(to_enrich), enriched)
            conn.commit()

        time.sleep(RATE_LIMIT_SECONDS)

    # Record source metadata.
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT OR REPLACE INTO data_sources
               (source_id, last_updated, entries_count, url, notes)
           VALUES ('steam', ?, ?, ?, 'Steam Store API — app details')""",
        (now, enriched, STEAM_APP_DETAILS_URL),
    )

    conn.commit()
    conn.close()
    logger.info("Steam fetch complete: %d games enriched", enriched)
    return enriched


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    db = Path(__file__).parent.parent / "data" / "linuxplaydb.db"
    if not db.exists():
        print(f"ERROR: Database not found at {db}", file=sys.stderr)
        sys.exit(1)
    count = fetch(db)
    print(f"Enriched {count} games from Steam")
