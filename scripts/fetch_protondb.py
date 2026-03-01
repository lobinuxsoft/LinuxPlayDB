#!/usr/bin/env python3
"""Fetch ProtonDB compatibility tiers for games in the database.

Only queries games that already exist with real (positive) Steam app_ids.
Respects rate limits: 1 request per second.

Usage:
    python fetch_protondb.py                      # Standalone
    from fetch_protondb import fetch; fetch(db_path)  # As module
"""

import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

PROTONDB_API = "https://www.protondb.com/api/v1/reports/summaries/{appid}.json"

# Rate limit: 1 request per second.
RATE_LIMIT_SECONDS = 1.0

# Timeout per request (seconds).
REQUEST_TIMEOUT = 10

# Valid ProtonDB tiers (in quality order).
VALID_TIERS = {"platinum", "gold", "silver", "bronze", "borked", "pending", "native"}


def _get_eligible_app_ids(cur: sqlite3.Cursor) -> list[int]:
    """Return all positive app_ids from the games table (real Steam IDs)."""
    cur.execute("SELECT app_id FROM games WHERE app_id > 0 ORDER BY app_id")
    return [row[0] for row in cur.fetchall()]


def fetch(db_path: Path) -> int:
    """Fetch ProtonDB tiers and update linux_compat.protondb_tier.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of entries successfully updated.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    app_ids = _get_eligible_app_ids(cur)
    if not app_ids:
        logger.warning("No games with positive app_ids found — nothing to fetch")
        conn.close()
        return 0

    logger.info("Fetching ProtonDB tiers for %d games (rate: 1 req/s)", len(app_ids))

    updated = 0
    errors = 0
    session = requests.Session()
    session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})

    for i, app_id in enumerate(app_ids):
        url = PROTONDB_API.format(appid=app_id)

        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 404:
                # Game not on ProtonDB — skip silently.
                logger.debug("App %d: not found on ProtonDB", app_id)
            elif resp.status_code == 429:
                # Rate limited — back off and retry once.
                logger.warning("Rate limited at app %d, backing off 5s", app_id)
                time.sleep(5)
                resp = session.get(url, timeout=REQUEST_TIMEOUT)
                if resp.status_code == 200:
                    tier = resp.json().get("tier", "").lower()
                    if tier in VALID_TIERS:
                        _upsert_tier(cur, app_id, tier)
                        updated += 1
            elif resp.status_code == 200:
                data = resp.json()
                tier = data.get("tier", "").lower()
                if tier in VALID_TIERS:
                    _upsert_tier(cur, app_id, tier)
                    updated += 1
                else:
                    logger.debug("App %d: unknown tier '%s'", app_id, tier)
            else:
                logger.warning("App %d: HTTP %d", app_id, resp.status_code)
                errors += 1

        except requests.RequestException as exc:
            logger.warning("App %d: request failed: %s", app_id, exc)
            errors += 1

        # Progress reporting every 50 games.
        if (i + 1) % 50 == 0:
            logger.info("Progress: %d/%d (updated: %d, errors: %d)", i + 1, len(app_ids), updated, errors)
            conn.commit()  # Intermediate commit for safety.

        # Rate limit.
        time.sleep(RATE_LIMIT_SECONDS)

    # Record source metadata.
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT OR REPLACE INTO data_sources
               (source_id, last_updated, entries_count, url, notes)
           VALUES ('protondb', ?, ?, ?, 'ProtonDB tier summaries')""",
        (now, updated, "https://www.protondb.com/api/v1/reports/summaries/"),
    )

    conn.commit()
    conn.close()
    logger.info("ProtonDB fetch complete: %d updated, %d errors out of %d total", updated, errors, len(app_ids))
    return updated


def _upsert_tier(cur: sqlite3.Cursor, app_id: int, tier: str) -> None:
    """Upsert the protondb_tier into linux_compat."""
    cur.execute(
        """INSERT INTO linux_compat (app_id, protondb_tier)
           VALUES (?, ?)
           ON CONFLICT(app_id) DO UPDATE SET protondb_tier = excluded.protondb_tier""",
        (app_id, tier),
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    db = Path(__file__).parent.parent / "data" / "linuxplaydb.db"
    if not db.exists():
        print(f"ERROR: Database not found at {db}", file=sys.stderr)
        sys.exit(1)
    count = fetch(db)
    print(f"Updated {count} ProtonDB entries")
