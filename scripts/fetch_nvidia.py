#!/usr/bin/env python3
"""Fetch NVIDIA RTX/DLSS game database.

Source: NVIDIA's official RTX games/apps JSON endpoint.
Filters for type == "Game" with any ray tracing or DLSS data,
then upserts into games + graphics_features tables.

Usage:
    python fetch_nvidia.py                  # Standalone
    from fetch_nvidia import fetch; fetch(db_path)  # As module
"""

import logging
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

NVIDIA_URL = (
    "https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/news/"
    "nvidia-rtx-games-engines-apps/dlss-rt-games-apps-overrides.json"
)

# Timeout for the HTTP request (seconds).
REQUEST_TIMEOUT = 30


def _has_value(field: str) -> bool:
    """Check if an NVIDIA JSON field has a truthy value (not empty string)."""
    return bool(field and field.strip())


def _parse_rt_type(ray_tracing: str) -> str:
    """Map NVIDIA ray_tracing field to our rt_type enum."""
    if not ray_tracing or not ray_tracing.strip():
        return "none"
    val = ray_tracing.strip().lower()
    if "path tracing" in val:
        return "pt"
    if "full rt" in val:
        return "rt"
    # Generic "Yes" or any other truthy value.
    return "rt"


def _find_game_by_name(cur: sqlite3.Cursor, name: str) -> int | None:
    """Find a game by exact name match. Returns app_id or None."""
    cur.execute("SELECT app_id FROM games WHERE name = ?", (name,))
    row = cur.fetchone()
    return row[0] if row else None


def _generate_placeholder_id(name: str) -> int:
    """Generate a stable negative app_id from name (placeholder until Steam resolves it)."""
    return -(abs(hash(name)) % 900000 + 100000)


def fetch(db_path: Path) -> int:
    """Fetch NVIDIA RTX data and upsert into the database.

    Args:
        db_path: Path to the SQLite database file.

    Returns:
        Number of game entries processed.
    """
    logger.info("Fetching NVIDIA RTX database from %s", NVIDIA_URL)

    try:
        resp = requests.get(NVIDIA_URL, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.error("Failed to fetch NVIDIA data: %s", exc)
        return 0

    try:
        payload = resp.json()
    except ValueError as exc:
        logger.error("Failed to parse NVIDIA JSON: %s", exc)
        return 0

    entries = payload.get("data", [])
    if not entries:
        logger.warning("NVIDIA JSON has no 'data' array or it is empty")
        return 0

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    processed = 0

    for entry in entries:
        entry_type = entry.get("type", "").strip()
        if entry_type != "Game":
            continue

        name = entry.get("name", "")
        if isinstance(name, int):
            name = str(name)
        name = name.strip()
        if not name:
            continue

        rt_raw = entry.get("ray_tracing", "")
        dlss_sr_raw = entry.get("dlss_super_resolution", "")
        dlss_fg_raw = entry.get("dlss_frame_generation", "")
        dlss_rr_raw = entry.get("dlss_ray_reconstruction", "")
        dlss_mfg_raw = entry.get("dlss_multi_frame_generation", "")
        dlaa_raw = entry.get("dlaa", "")

        # Skip entries with zero useful data.
        has_any = any(
            _has_value(f)
            for f in [rt_raw, dlss_sr_raw, dlss_fg_raw, dlss_rr_raw, dlss_mfg_raw, dlaa_raw]
        )
        if not has_any:
            continue

        rt_type = _parse_rt_type(rt_raw)
        dlss_sr = int(_has_value(dlss_sr_raw))
        dlss_fg = int(_has_value(dlss_fg_raw))
        dlss_rr = int(_has_value(dlss_rr_raw))
        dlss_mfg = int(_has_value(dlss_mfg_raw))
        dlaa = int(_has_value(dlaa_raw))

        # Try to match existing game or create a new one.
        app_id = _find_game_by_name(cur, name)
        if app_id is None:
            app_id = _generate_placeholder_id(name)
            cur.execute(
                "INSERT OR IGNORE INTO games (app_id, name, type) VALUES (?, ?, 'game')",
                (app_id, name),
            )

        # Upsert graphics features — preserve existing FSR/XeSS data.
        cur.execute(
            """INSERT INTO graphics_features
                   (app_id, rt_type, dlss_sr, dlss_fg, dlss_rr, dlss_mfg, dlaa)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(app_id) DO UPDATE SET
                   rt_type  = CASE WHEN excluded.rt_type != 'none'
                                   THEN excluded.rt_type ELSE graphics_features.rt_type END,
                   dlss_sr  = MAX(graphics_features.dlss_sr,  excluded.dlss_sr),
                   dlss_fg  = MAX(graphics_features.dlss_fg,  excluded.dlss_fg),
                   dlss_rr  = MAX(graphics_features.dlss_rr,  excluded.dlss_rr),
                   dlss_mfg = MAX(graphics_features.dlss_mfg, excluded.dlss_mfg),
                   dlaa     = MAX(graphics_features.dlaa,     excluded.dlaa)
            """,
            (app_id, rt_type, dlss_sr, dlss_fg, dlss_rr, dlss_mfg, dlaa),
        )

        processed += 1

    # Record source metadata.
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT OR REPLACE INTO data_sources
               (source_id, last_updated, entries_count, url, notes)
           VALUES ('nvidia', ?, ?, ?, 'NVIDIA RTX/DLSS database')""",
        (now, processed, NVIDIA_URL),
    )

    conn.commit()
    conn.close()
    logger.info("NVIDIA fetch complete: %d games processed", processed)
    return processed


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    db = Path(__file__).parent.parent / "data" / "linuxplaydb.db"
    if not db.exists():
        print(f"ERROR: Database not found at {db}", file=sys.stderr)
        sys.exit(1)
    count = fetch(db)
    print(f"Processed {count} NVIDIA game entries")
