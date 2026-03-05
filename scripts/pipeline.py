#!/usr/bin/env python3
"""Incremental pipeline for LinuxPlayDB.

Processes games in configurable batches, accumulating data over the existing
database.  When all games are processed a new cycle starts (re-fetches the
full Steam catalog and resets progress).

Usage:
    python pipeline.py                    # Process next batch (default 1000)
    python pipeline.py --batch-size 500   # Custom batch size
    python pipeline.py --new-cycle        # Force a new cycle
    python pipeline.py --status           # Show pipeline status
"""

import argparse
import logging
import os
import shutil
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).parent.parent
SCRIPTS_DIR = ROOT / "scripts"
DATA_DIR = ROOT / "data"
DB_FILE = DATA_DIR / "linuxplaydb.db"

# Ensure scripts/ is on sys.path so we can import sibling modules.
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

logger = logging.getLogger("pipeline")

DEFAULT_BATCH_SIZE = 1000


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def ensure_db_exists() -> Path:
    """Create the database with schema + seed migration if it doesn't exist.

    Returns the path to the database file.
    """
    if DB_FILE.exists():
        # Just ensure schema is up-to-date (adds new tables/columns).
        from build_db import create_schema
        create_schema(DB_FILE)
        return DB_FILE

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    from build_db import create_schema
    create_schema(DB_FILE)

    from migrate_seed import migrate
    migrate(DB_FILE)

    logger.info("Created new database with seed data at %s", DB_FILE)
    return DB_FILE


def _db_connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Cycle management
# ---------------------------------------------------------------------------

def get_pipeline_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute(
        "SELECT value FROM pipeline_meta WHERE key = ?", (key,)
    ).fetchone()
    return row[0] if row else None


def set_pipeline_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO pipeline_meta (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()


def pending_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM pipeline_progress WHERE status = 'pending'"
    ).fetchone()
    return row[0]


def done_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM pipeline_progress WHERE status = 'done'"
    ).fetchone()
    return row[0]


def total_count(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM pipeline_progress").fetchone()
    return row[0]


def start_new_cycle(db_path: Path) -> str:
    """Begin a new processing cycle.

    1. Fetch the full Steam catalog (IStoreService) to discover new games.
    2. Fetch NVIDIA data (bulk) to discover RT games without Steam IDs.
    3. Reset pipeline_progress: all games -> pending.

    Returns the new cycle_id.
    """
    cycle_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    conn = _db_connect(db_path)

    api_key = os.environ.get("STEAM_API_KEY")
    if api_key:
        logger.info("Fetching full Steam catalog for new cycle...")
        from fetch_steam import fetch_all_apps, insert_new_apps
        import requests

        session = requests.Session()
        session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})
        all_apps = fetch_all_apps(session, api_key)
        inserted = insert_new_apps(conn, all_apps)
        logger.info("Steam catalog: %d total, %d new", len(all_apps), inserted)
    else:
        logger.warning("No STEAM_API_KEY — skipping catalog refresh")

    # Populate pipeline_progress with ALL game app_ids.
    conn.execute("DELETE FROM pipeline_progress")
    conn.execute(
        """INSERT INTO pipeline_progress (app_id, status, cycle_id)
           SELECT app_id, 'pending', ?
           FROM games WHERE app_id > 0""",
        (cycle_id,),
    )
    set_pipeline_meta(conn, "current_cycle", cycle_id)
    set_pipeline_meta(conn, "cycle_started_at",
                      datetime.now(timezone.utc).isoformat())
    conn.commit()

    total = pending_count(conn)
    conn.close()
    logger.info("New cycle %s started with %d games", cycle_id, total)
    return cycle_id


def get_next_batch(conn: sqlite3.Connection, size: int) -> list[int]:
    """Return the next batch of pending app_ids."""
    rows = conn.execute(
        "SELECT app_id FROM pipeline_progress WHERE status = 'pending' "
        "ORDER BY app_id LIMIT ?",
        (size,),
    ).fetchall()
    return [r[0] for r in rows]


def mark_batch_done(conn: sqlite3.Connection, app_ids: list[int]) -> None:
    """Mark a batch of app_ids as done."""
    now = datetime.now(timezone.utc).isoformat()
    conn.executemany(
        "UPDATE pipeline_progress SET status = 'done', processed_at = ? "
        "WHERE app_id = ?",
        [(now, aid) for aid in app_ids],
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def process_batch(db_path: Path, app_ids: list[int]) -> None:
    """Run all data sources against a batch of app_ids."""
    import requests

    session = requests.Session()
    session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})

    # 1. Steam appdetails — get name/type/description for each ID.
    try:
        from fetch_steam import fetch_details_for_ids
        fetch_details_for_ids(db_path, app_ids, session=session)
    except Exception as exc:
        logger.error("Steam details failed: %s", exc)

    # 2. NVIDIA — bulk download once, then match for batch.
    try:
        from fetch_nvidia import fetch_and_cache, match_for_ids
        nvidia_data = fetch_and_cache(session=session)
        if nvidia_data:
            match_for_ids(db_path, app_ids, nvidia_data)
    except Exception as exc:
        logger.error("NVIDIA match failed: %s", exc)

    # 3. Anti-cheat — bulk download once, then match for batch.
    try:
        from fetch_anticheat import fetch_and_cache_anticheat, match_anticheat_for_ids
        ac_data = fetch_and_cache_anticheat(session=session)
        if ac_data:
            match_anticheat_for_ids(db_path, app_ids, ac_data)
    except Exception as exc:
        logger.error("Anti-cheat match failed: %s", exc)

    # 4. Deck compat — per-ID requests (only for valid games).
    try:
        from fetch_deck_compat import fetch_for_ids as fetch_deck_for_ids
        fetch_deck_for_ids(db_path, app_ids, session=session)
    except Exception as exc:
        logger.error("Deck compat failed: %s", exc)

    # 5. ProtonDB — per-ID requests (community + official).
    try:
        from fetch_protondb_reports import fetch_for_ids as fetch_protondb_for_ids
        fetch_protondb_for_ids(db_path, app_ids)
    except Exception as exc:
        logger.error("ProtonDB failed: %s", exc)

    # 6. AI research — only for games with RT/PT features.
    api_key = os.environ.get("MISTRAL_API_KEY")
    if api_key:
        try:
            from research_with_ai import research_for_ids
            research_for_ids(db_path, app_ids)
        except Exception as exc:
            logger.error("AI research failed: %s", exc)
    else:
        logger.info("No MISTRAL_API_KEY — skipping AI research")


def finalize(db_path: Path) -> None:
    """Post-batch steps: manual overrides, devices, copy to site, inline DB."""
    from build_db import (
        load_manual_json,
        load_devices,
        update_data_sources,
        copy_to_site,
        generate_inline_db,
    )

    load_devices(db_path)
    load_manual_json(db_path)
    update_data_sources(db_path)
    copy_to_site(db_path)
    generate_inline_db(db_path)


# ---------------------------------------------------------------------------
# Status report
# ---------------------------------------------------------------------------

def print_status(db_path: Path) -> None:
    """Print current pipeline status."""
    if not db_path.exists():
        print("No database found. Run the pipeline to create one.")
        return

    # Ensure pipeline tables exist in an older DB.
    from build_db import create_schema
    create_schema(db_path)

    conn = _db_connect(db_path)

    cycle = get_pipeline_meta(conn, "current_cycle")
    started = get_pipeline_meta(conn, "cycle_started_at")
    p = pending_count(conn)
    d = done_count(conn)
    t = total_count(conn)

    print("=" * 50)
    print("PIPELINE STATUS")
    print("=" * 50)
    if cycle:
        print(f"  Cycle:   {cycle}")
        print(f"  Started: {started}")
    else:
        print("  No cycle active")
    print(f"  Total:   {t}")
    print(f"  Done:    {d}")
    print(f"  Pending: {p}")
    if t > 0:
        print(f"  Progress: {d / t * 100:.1f}%")

    # Games table stats.
    row = conn.execute("SELECT COUNT(*) FROM games").fetchone()
    print(f"\n  Games in DB: {row[0]}")

    # Research snapshots stats.
    try:
        rs_total = conn.execute(
            "SELECT COUNT(*) FROM research_snapshots"
        ).fetchone()[0]
        rs_researched = conn.execute(
            "SELECT COUNT(*) FROM research_snapshots "
            "WHERE ai_researched_at IS NOT NULL"
        ).fetchone()[0]
        rs_with_protondb = conn.execute(
            "SELECT COUNT(*) FROM research_snapshots "
            "WHERE protondb_total IS NOT NULL"
        ).fetchone()[0]
        rs_stale = conn.execute(
            """SELECT COUNT(*) FROM research_snapshots
               WHERE ai_researched_at IS NOT NULL
                 AND ((protondb_total IS NOT NULL
                       AND protondb_total_at_research IS NOT NULL
                       AND protondb_total - protondb_total_at_research >= 10)
                      OR (protondb_tier IS NOT NULL
                          AND protondb_tier_at_research IS NOT NULL
                          AND protondb_tier != protondb_tier_at_research))"""
        ).fetchone()[0]
        print(f"\n  Research snapshots: {rs_total}")
        print(f"    AI researched:   {rs_researched}")
        print(f"    ProtonDB data:   {rs_with_protondb}")
        print(f"    Stale (need re-research): {rs_stale}")
    except sqlite3.OperationalError:
        pass  # table doesn't exist yet

    size = db_path.stat().st_size
    print(f"\n  DB size: {size / 1024:.1f} KB")
    print("=" * 50)

    conn.close()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="LinuxPlayDB incremental pipeline"
    )
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
                        help=f"Games per batch (default: {DEFAULT_BATCH_SIZE})")
    parser.add_argument("--new-cycle", action="store_true",
                        help="Force a new processing cycle")
    parser.add_argument("--status", action="store_true",
                        help="Print pipeline status and exit")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Status check — no processing.
    if args.status:
        print_status(DB_FILE)
        return

    start = time.time()
    logger.info("LinuxPlayDB — Incremental Pipeline")

    # 1. Ensure database exists.
    db_path = ensure_db_exists()

    conn = _db_connect(db_path)

    # 2. Start new cycle if forced or no pending work.
    if args.new_cycle or pending_count(conn) == 0:
        conn.close()
        start_new_cycle(db_path)
        conn = _db_connect(db_path)

    # 3. Get next batch.
    batch = get_next_batch(conn, args.batch_size)
    if not batch:
        logger.info("No pending games. Pipeline is idle.")
        conn.close()
        finalize(db_path)
        logger.info("Finalized in %.1fs", time.time() - start)
        return

    p = pending_count(conn)
    logger.info("Processing batch of %d games (%d pending)", len(batch), p)
    conn.close()

    # 4. Process the batch.
    process_batch(db_path, batch)

    # 5. Mark as done.
    conn = _db_connect(db_path)
    mark_batch_done(conn, batch)
    logger.info("Batch complete: %d done, %d remaining",
                len(batch), pending_count(conn))
    conn.close()

    # 6. Finalize: manual overrides, devices, copy to site.
    finalize(db_path)

    elapsed = time.time() - start
    logger.info("Pipeline run complete in %.1f minutes", elapsed / 60)


if __name__ == "__main__":
    main()
