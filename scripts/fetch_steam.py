#!/usr/bin/env python3
"""Fetch complete Steam game catalog.

Three-phase approach:
1. IStoreService/GetAppList/v1 — ALL app IDs (~120K), needs STEAM_API_KEY
2. SteamSpy API — names + metadata for ~27K popular games (no key needed)
3. Steam appdetails — incremental name/detail resolution (rate limited)

Usage:
    export STEAM_API_KEY="your-key"
    python fetch_steam.py                         # Full pipeline
    python fetch_steam.py --skip-steamspy         # Skip SteamSpy (~30 min savings)
    python fetch_steam.py --skip-details          # Skip slow appdetails phase
    python fetch_steam.py --details-limit 1000    # Limit detail requests
    from fetch_steam import fetch; fetch(db_path) # As module
"""

import argparse
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

# API endpoints
STORE_SERVICE_URL = "https://api.steampowered.com/IStoreService/GetAppList/v1/"
STEAMSPY_ALL_URL = "https://steamspy.com/api.php"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"

# Rate limits
STEAMSPY_DELAY = 1.2      # SteamSpy: 1 req/sec for individual, 1 req/min for "all"
DETAILS_DELAY = 1.6        # Steam appdetails: ~200 req/5 min
DETAILS_BACKOFF = 35       # Backoff on 429

# Defaults
MAX_DETAIL_REQUESTS = 500  # Per run (safety cap)
REQUEST_TIMEOUT = 20


def _fetch_all_apps(session: requests.Session, api_key: str) -> dict[int, str]:
    """Fetch ALL Steam apps via IStoreService/GetAppList (paginated).

    Returns {appid: name} for games only. Names come free from the API.
    """
    all_apps: dict[int, str] = {}
    last_appid = 0
    page = 0

    while True:
        page += 1
        params = {
            "key": api_key,
            "max_results": 50000,
            "include_games": "true",
            "include_dlc": "false",
            "include_software": "false",
            "include_videos": "false",
            "include_hardware": "false",
        }
        if last_appid > 0:
            params["last_appid"] = last_appid

        try:
            resp = session.get(STORE_SERVICE_URL, params=params, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as exc:
            logger.error("IStoreService page %d failed: %s", page, exc)
            break

        data = resp.json().get("response", {})
        apps = data.get("apps", [])
        if not apps:
            break

        for app in apps:
            all_apps[app["appid"]] = app.get("name", "")

        last_appid = apps[-1]["appid"]
        have_more = data.get("have_more_results", False)

        logger.info("  Page %d: %d apps (total: %d, last_appid: %d)",
                     page, len(apps), len(all_apps), last_appid)

        if not have_more:
            break

        time.sleep(0.5)

    return all_apps


def _fetch_steamspy_names(session: requests.Session) -> dict[int, dict]:
    """Fetch game names and basic data from SteamSpy (all pages).

    Returns {appid: {"name": str, "positive": int, "negative": int, ...}}.
    """
    all_games = {}
    page = 0

    while True:
        try:
            resp = session.get(
                STEAMSPY_ALL_URL,
                params={"request": "all", "page": page},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            logger.warning("SteamSpy page %d failed: %s", page, exc)
            break

        if not data:
            break

        for appid_str, info in data.items():
            try:
                appid = int(appid_str)
            except (ValueError, TypeError):
                continue
            name = info.get("name", "").strip()
            if name:
                all_games[appid] = {
                    "name": name,
                    "positive": info.get("positive", 0),
                    "negative": info.get("negative", 0),
                    "owners": info.get("owners", ""),
                }

        count = len(data)
        logger.info("  SteamSpy page %d: %d games (total: %d)", page, count, len(all_games))

        if count < 1000:
            # Last page
            break

        page += 1
        time.sleep(65)  # SteamSpy requires 1 min between "all" requests

    return all_games


def _fetch_app_details(session: requests.Session, app_id: int) -> dict | None:
    """Fetch details for a single app from Steam Store API."""
    try:
        resp = session.get(
            STEAM_DETAILS_URL,
            params={"appids": str(app_id), "filters": "basic"},
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code == 429:
            logger.warning("Rate limited on %d, backing off %ds", app_id, DETAILS_BACKOFF)
            time.sleep(DETAILS_BACKOFF)
            return None
        resp.raise_for_status()
    except requests.RequestException:
        return None

    try:
        payload = resp.json()
    except ValueError:
        return None

    app_data = payload.get(str(app_id), {})
    if not app_data.get("success"):
        return None

    return app_data.get("data", {})


def fetch(db_path: Path, api_key: str | None = None,
          skip_details: bool = False, details_limit: int = MAX_DETAIL_REQUESTS,
          skip_steamspy: bool = False) -> int:
    """Fetch Steam catalog and populate the database.

    Returns total number of games in DB after fetch.
    """
    if not api_key:
        api_key = os.environ.get("STEAM_API_KEY")

    session = requests.Session()
    session.headers.update({"User-Agent": "LinuxPlayDB/1.0"})

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Get existing games
    cur.execute("SELECT app_id, name FROM games")
    existing_by_id = {}
    existing_by_name = {}
    for row in cur.fetchall():
        existing_by_id[row[0]] = row[1]
        existing_by_name[row[1].strip().lower()] = row[0]

    total_before = len(existing_by_id)
    inserted = 0
    resolved = 0

    # ── Phase 1: Get ALL app IDs + names from Steam ──
    if api_key:
        print("[Phase 1] Fetching all Steam games (IStoreService)...")
        all_apps = _fetch_all_apps(session, api_key)
        print(f"  Found {len(all_apps)} games from Steam")

        # Insert new games with names from IStoreService
        new_count = 0
        named_from_api = 0
        batch = 0
        for aid, api_name in all_apps.items():
            if aid not in existing_by_id:
                # New game — use API name if available, placeholder otherwise
                name = api_name.strip() if api_name else f"[Steam App {aid}]"
                cur.execute(
                    "INSERT OR IGNORE INTO games (app_id, name, type) VALUES (?, ?, 'game')",
                    (aid, name),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO linux_compat (app_id, linux_status) VALUES (?, 'check')",
                    (aid,),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO graphics_features (app_id) VALUES (?)",
                    (aid,),
                )
                new_count += 1
                if api_name.strip():
                    named_from_api += 1
            else:
                # Existing game — update placeholder names with real names from API
                current_name = existing_by_id[aid]
                if current_name.startswith("[Steam App ") and api_name.strip():
                    cur.execute("UPDATE games SET name = ? WHERE app_id = ?",
                                (api_name.strip(), aid))
                    named_from_api += 1
            batch += 1
            if batch % 5000 == 0:
                conn.commit()
                print(f"  Progress: {batch}/{len(all_apps)} ({new_count} new)")
        conn.commit()
        print(f"  Inserted {new_count} new games ({named_from_api} with names from API)")
        inserted += new_count
    else:
        print("[Phase 1] SKIP — no STEAM_API_KEY set")

    # ── Phase 2: Get names from SteamSpy (slow — optional in CI) ──
    if not skip_steamspy:
        print("[Phase 2] Fetching game names from SteamSpy...")
        spy_data = _fetch_steamspy_names(session)
        print(f"  SteamSpy returned {len(spy_data)} games with names")

        named = 0
        for appid, info in spy_data.items():
            name = info["name"]

            if appid in existing_by_id:
                # Update name if it's a placeholder
                current_name = existing_by_id[appid]
                if current_name.startswith("[Steam App "):
                    cur.execute("UPDATE games SET name = ? WHERE app_id = ?", (name, appid))
                    named += 1
            else:
                # New game from SteamSpy not in Steam list
                cur.execute(
                    "INSERT OR IGNORE INTO games (app_id, name, type) VALUES (?, ?, 'game')",
                    (appid, name),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO linux_compat (app_id, linux_status) VALUES (?, 'check')",
                    (appid,),
                )
                cur.execute(
                    "INSERT OR IGNORE INTO graphics_features (app_id) VALUES (?)",
                    (appid,),
                )
                inserted += 1
                named += 1

        conn.commit()
        print(f"  Named {named} games from SteamSpy")
    else:
        spy_data = {}
        print("[Phase 2] SKIP — --skip-steamspy flag")

    # Resolve placeholder IDs: match negative-ID games by name to real IDs
    cur.execute("SELECT app_id, name FROM games WHERE app_id < 0")
    placeholders = cur.fetchall()
    for old_id, name in placeholders:
        name_lower = name.strip().lower()
        # Find real ID from SteamSpy data (if available)
        real_id = None
        for sid, info in spy_data.items():
            if info["name"].strip().lower() == name_lower:
                real_id = sid
                break

        if not real_id:
            # Try from Steam IDs we just fetched
            cur.execute(
                "SELECT app_id FROM games WHERE app_id > 0 AND LOWER(name) = ?",
                (name_lower,),
            )
            row = cur.fetchone()
            if row:
                real_id = row[0]

        if real_id and real_id != old_id:
            # Check if real_id already exists
            cur.execute("SELECT 1 FROM games WHERE app_id = ?", (real_id,))
            if cur.fetchone():
                # Merge: move data from placeholder to real entry, then delete placeholder
                for table in ("graphics_features", "linux_compat"):
                    cur.execute(f"DELETE FROM {table} WHERE app_id = ?", (old_id,))
                cur.execute("UPDATE useful_links SET app_id = ? WHERE app_id = ?", (real_id, old_id))
                cur.execute("UPDATE device_compat SET app_id = ? WHERE app_id = ?", (real_id, old_id))
                cur.execute("DELETE FROM games WHERE app_id = ?", (old_id,))
            else:
                # Swap ID across all tables
                for table in ("games", "graphics_features", "linux_compat", "device_compat", "useful_links"):
                    cur.execute(f"UPDATE {table} SET app_id = ? WHERE app_id = ?", (real_id, old_id))
            resolved += 1

    conn.commit()
    print(f"  Resolved {resolved} placeholder IDs")

    # ── Phase 3: Incremental detail fetch for unnamed games ──
    if not skip_details:
        cur.execute(
            """SELECT app_id FROM games
               WHERE app_id > 0 AND name LIKE '[Steam App %]'
               ORDER BY app_id
               LIMIT ?""",
            (details_limit,),
        )
        unnamed = [row[0] for row in cur.fetchall()]

        if unnamed:
            print(f"[Phase 3] Fetching names for {len(unnamed)} games via Steam appdetails...")
            details_ok = 0
            for i, appid in enumerate(unnamed):
                data = _fetch_app_details(session, appid)
                if data:
                    name = data.get("name", "").strip()
                    app_type = data.get("type", "game")
                    short_desc = data.get("short_description", "").strip() or None
                    if name:
                        cur.execute(
                            "UPDATE games SET name = ?, type = ?, short_description = COALESCE(?, short_description) WHERE app_id = ?",
                            (name, app_type, short_desc, appid),
                        )
                        # If it's not a game (DLC, demo, etc.), mark it
                        if app_type not in ("game",):
                            cur.execute(
                                "UPDATE games SET type = ? WHERE app_id = ?",
                                (app_type, appid),
                            )
                        details_ok += 1
                    else:
                        # Remove entries that aren't valid games
                        cur.execute("DELETE FROM graphics_features WHERE app_id = ?", (appid,))
                        cur.execute("DELETE FROM linux_compat WHERE app_id = ?", (appid,))
                        cur.execute("DELETE FROM games WHERE app_id = ?", (appid,))

                if (i + 1) % 50 == 0:
                    conn.commit()
                    print(f"  Progress: {i + 1}/{len(unnamed)} ({details_ok} named)")

                time.sleep(DETAILS_DELAY)

            conn.commit()
            print(f"  Named {details_ok}/{len(unnamed)} games via appdetails")
        else:
            print("[Phase 3] SKIP — no unnamed games remaining")
    else:
        print("[Phase 3] SKIP — --skip-details flag")

    # Record metadata
    cur.execute("SELECT COUNT(*) FROM games")
    total_after = cur.fetchone()[0]
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT OR REPLACE INTO data_sources
               (source_id, last_updated, entries_count, url, notes)
           VALUES ('steam', ?, ?, ?, 'Steam IStoreService + SteamSpy + appdetails')""",
        (now, total_after, STORE_SERVICE_URL),
    )
    conn.commit()
    conn.close()

    print(f"\n[OK] Steam fetch complete: {total_before} → {total_after} games "
          f"(+{inserted} new, {resolved} resolved)")
    return total_after


def main():
    parser = argparse.ArgumentParser(description="Fetch complete Steam game catalog")
    parser.add_argument("--skip-details", action="store_true",
                        help="Skip slow Steam appdetails phase")
    parser.add_argument("--skip-steamspy", action="store_true",
                        help="Skip SteamSpy name resolution (~30 min savings)")
    parser.add_argument("--details-limit", type=int, default=MAX_DETAIL_REQUESTS,
                        help=f"Max appdetails requests per run (default: {MAX_DETAIL_REQUESTS})")
    parser.add_argument("--db", type=Path,
                        default=Path(__file__).parent.parent / "data" / "linuxplaydb.db")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.db.exists():
        print(f"[ERROR] Database not found: {args.db}")
        sys.exit(1)

    fetch(args.db, skip_details=args.skip_details, details_limit=args.details_limit,
          skip_steamspy=args.skip_steamspy)


if __name__ == "__main__":
    main()
