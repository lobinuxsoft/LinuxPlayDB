#!/usr/bin/env python3
"""Fetch Steam Deck compatibility status for games in the database.

Uses Steam's Deck compatibility report endpoint to check verified/playable/
unsupported/unknown status. Only queries games with real (positive) app_ids.

Rate limit: ~200 requests per 5 minutes (throttled to ~1.5s between requests).

Usage:
    python fetch_deck_compat.py                          # Standalone
    from fetch_deck_compat import fetch; fetch(db_path)  # As module
"""

import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

DECK_COMPAT_URL = (
    "https://store.steampowered.com/saleaction/"
    "ajaxgetdeckappcompatibilityreport"
)

# ~200 requests per 5 min.
RATE_LIMIT_SECONDS = 1.5

# Timeout per request (seconds).
REQUEST_TIMEOUT = 10

# Steam Deck compatibility categories.
# See: https://partner.steamgames.com/doc/steamdeck/compat
COMPAT_CATEGORIES = {
    0: "unknown",
    1: "unsupported",
    2: "playable",
    3: "verified",
}

# Safety cap per run.
MAX_REQUESTS = 500


def _get_eligible_app_ids(cur: sqlite3.Cursor) -> list[int]:
    """Return positive app_ids that don't have deck_status yet (or need refresh)."""
    cur.execute(
        """SELECT g.app_id FROM games g
           LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
           WHERE g.app_id > 0
             AND (lc.deck_status IS NULL OR lc.deck_status = 'unknown')
           ORDER BY g.app_id
           LIMIT ?""",
        (MAX_REQUESTS,),
    )
    return [row[0] for row in cur.fetchall()]


def _parse_compat_category(data) -> str:
    """Extract the compatibility category from the API response."""
    if not isinstance(data, dict):
        return "unknown"

    # The response structure can vary; handle known formats.
    results = data.get("results", {})
    if not isinstance(results, dict):
        return "unknown"

    # Primary: look for resolved_category.
    resolved = results.get("resolved_category")
    if resolved is not None:
        return COMPAT_CATEGORIES.get(resolved, "unknown")

    # Fallback: check success and look at the raw response.
    if data.get("success") == 1:
        # Sometimes the category is at the top level.
        category = data.get("resolved_category")
        if category is not None:
            return COMPAT_CATEGORIES.get(category, "unknown")

    return "unknown"


def fetch(db_path: Path) -> int:
    """Fetch Deck compatibility and update linux_compat.deck_status.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of entries updated.
    """
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        app_ids = _get_eligible_app_ids(cur)
        if not app_ids:
            logger.info("No games need Deck compat check")
            return 0

        logger.info("Checking Deck compatibility for %d games", len(app_ids))

        session = requests.Session()
        session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})

        updated = 0
        errors = 0

        for i, app_id in enumerate(app_ids):
            try:
                resp = session.get(
                    DECK_COMPAT_URL,
                    params={"nAppID": app_id},
                    timeout=REQUEST_TIMEOUT,
                )

                if resp.status_code == 429:
                    logger.warning("Rate limited at app %d, backing off 30s", app_id)
                    time.sleep(30)
                    continue

                if resp.status_code != 200:
                    logger.debug("App %d: HTTP %d", app_id, resp.status_code)
                    errors += 1
                    time.sleep(RATE_LIMIT_SECONDS)
                    continue

                data = resp.json()
                status = _parse_compat_category(data)

                if status != "unknown":
                    cur.execute(
                        """INSERT INTO linux_compat (app_id, deck_status)
                           VALUES (?, ?)
                           ON CONFLICT(app_id) DO UPDATE SET deck_status = excluded.deck_status""",
                        (app_id, status),
                    )
                    updated += 1

            except requests.RequestException as exc:
                logger.warning("App %d: request failed: %s", app_id, exc)
                errors += 1
            except (ValueError, KeyError) as exc:
                logger.warning("App %d: parse error: %s", app_id, exc)
                errors += 1

            # Progress + intermediate commit every 50 games.
            if (i + 1) % 50 == 0:
                logger.info("Progress: %d/%d (updated: %d, errors: %d)", i + 1, len(app_ids), updated, errors)
                conn.commit()

            time.sleep(RATE_LIMIT_SECONDS)

        # Record source metadata.
        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            """INSERT OR REPLACE INTO data_sources
                   (source_id, last_updated, entries_count, url, notes)
               VALUES ('deck_compat', ?, ?, ?, 'Steam Deck compatibility reports')""",
            (now, updated, DECK_COMPAT_URL),
        )

        conn.commit()
        logger.info("Deck compat fetch complete: %d updated, %d errors out of %d total", updated, errors, len(app_ids))
        return updated
    finally:
        conn.close()


def fetch_for_ids(db_path: Path, app_ids: list[int],
                  session: requests.Session | None = None) -> int:
    """Fetch Deck compatibility for a specific list of app_ids.

    Only queries games that don't already have a non-unknown deck_status.
    Returns number of entries updated.
    """
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()

        # Filter to IDs that need a Deck compat check.
        placeholders = ",".join("?" * len(app_ids))
        cur.execute(
            f"""SELECT g.app_id FROM games g
                LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
                WHERE g.app_id IN ({placeholders})
                  AND g.app_id > 0
                  AND (lc.deck_status IS NULL OR lc.deck_status = 'unknown')""",
            app_ids,
        )
        eligible = [r[0] for r in cur.fetchall()]

        if not eligible:
            return 0

        logger.info("Deck compat: checking %d/%d games", len(eligible), len(app_ids))

        updated = 0
        for i, app_id in enumerate(eligible):
            try:
                resp = session.get(
                    DECK_COMPAT_URL,
                    params={"nAppID": app_id},
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 429:
                    logger.warning("Deck compat rate limited at %d, backing off 30s", app_id)
                    time.sleep(30)
                    continue
                if resp.status_code != 200:
                    time.sleep(RATE_LIMIT_SECONDS)
                    continue

                data = resp.json()
                status = _parse_compat_category(data)

                if status != "unknown":
                    cur.execute(
                        """INSERT INTO linux_compat (app_id, deck_status)
                           VALUES (?, ?)
                           ON CONFLICT(app_id) DO UPDATE SET deck_status = excluded.deck_status""",
                        (app_id, status),
                    )
                    updated += 1

            except (requests.RequestException, ValueError, KeyError) as exc:
                logger.warning("Deck compat app %d failed: %s", app_id, exc)

            if (i + 1) % 50 == 0:
                conn.commit()
                logger.info("  Deck compat: %d/%d (%d updated)", i + 1, len(eligible), updated)

            time.sleep(RATE_LIMIT_SECONDS)

        now = datetime.now(timezone.utc).isoformat()
        cur.execute(
            """INSERT OR REPLACE INTO data_sources
                   (source_id, last_updated, entries_count, url, notes)
               VALUES ('deck_compat', ?, ?, ?, 'Steam Deck compatibility reports')""",
            (now, updated, DECK_COMPAT_URL),
        )

        conn.commit()
        logger.info("Deck compat: %d updated out of %d eligible", updated, len(eligible))
        return updated
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    db = Path(__file__).parent.parent / "data" / "linuxplaydb.db"
    if not db.exists():
        print(f"ERROR: Database not found at {db}", file=sys.stderr)
        sys.exit(1)
    count = fetch(db)
    print(f"Updated {count} Deck compat entries")
