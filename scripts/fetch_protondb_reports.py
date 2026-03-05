#!/usr/bin/env python3
"""Fetch ProtonDB user reports and extract launch configs.

Uses two sources:
1. ProtonDB Community API (protondb.max-p.me) — full user reports with notes/specs
2. ProtonDB Official summaries API — tier ratings

Extracts launch options, environment variables, and Proton versions from user reports.

Usage:
    python fetch_protondb_reports.py                    # Fetch all games in DB
    python fetch_protondb_reports.py --app-id 1182900   # Fetch specific Steam app ID
    python fetch_protondb_reports.py --limit 50         # Limit to 50 games
    python fetch_protondb_reports.py --reset-progress   # Wipe progress and re-fetch
    python fetch_protondb_reports.py --retry-failed     # Re-try only failed games
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("[ERROR] requests not installed. Run: pip install requests")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
DB_FILE = ROOT / "data" / "linuxplaydb.db"
MANUAL_DIR = ROOT / "scripts" / "manual"
OUTPUT_DIR = ROOT / "scripts" / "research_output"
PROGRESS_FILE = OUTPUT_DIR / "protondb_progress.json"

CHECKPOINT_INTERVAL = 50  # save partial results every N games

COMMUNITY_API = "https://protondb.max-p.me"
OFFICIAL_API = "https://www.protondb.com/api/v1/reports/summaries"

# Rate limits
REQUEST_DELAY = 1.0  # seconds between API calls

# Known env var patterns to extract from report notes
ENV_VAR_PATTERN = re.compile(
    r'\b((?:PROTON|VKD3D|DXVK|RADV|MESA|WINE|AMD|STEAM|MANGOHUD|ENABLE|DISABLE|'
    r'STAGING|DRI|GALLIUM|__GL|WINEESYNC|WINEFSYNC|WINEDLLOVERRIDES|SteamDeck)'
    r'[A-Z0-9_]*)\s*=\s*([^\s,;]+)',
    re.IGNORECASE
)

# Launch option patterns
LAUNCH_OPT_PATTERN = re.compile(
    r'(%command%.*|.*%command%|gamescope\s+.*|gamemoderun\s+.*|mangohud\s+.*)',
    re.IGNORECASE
)

# Proton version patterns
PROTON_VER_PATTERN = re.compile(
    r'((?:GE-)?Proton[\s-]*(?:Experimental|Hotfix|\d[\d.\-]*(?:GE)?(?:-\d+)?)|'
    r'Proton\s+\d[\d.]*)',
    re.IGNORECASE
)


def load_progress() -> tuple[set[int], set[int]]:
    """Load sets of succeeded and failed app_ids from progress file.

    Returns (succeeded_ids, failed_ids).
    """
    if PROGRESS_FILE.exists():
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            return (set(data.get("succeeded_ids", [])),
                    set(data.get("failed_ids", [])))
        except (json.JSONDecodeError, KeyError):
            return set(), set()
    return set(), set()


def save_progress(succeeded_ids: set[int], failed_ids: set[int]) -> None:
    """Persist the sets of succeeded/failed app_ids to disk."""
    PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "succeeded": len(succeeded_ids),
        "failed": len(failed_ids),
        "succeeded_ids": sorted(succeeded_ids),
        "failed_ids": sorted(failed_ids),
    }
    PROGRESS_FILE.write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def get_games_from_db(db_path: Path, steam_app_id: int | None = None,
                      limit: int | None = None,
                      exclude_ids: set[int] | None = None) -> list[dict]:
    """Get games from DB. Returns list with internal app_id, name, and steam_app_id if available."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if steam_app_id:
        # Direct Steam app ID lookup
        cur.execute("SELECT app_id, name FROM games WHERE app_id = ?", (steam_app_id,))
    else:
        cur.execute("""
            SELECT g.app_id, g.name
            FROM games g
            LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
            WHERE g.type = 'game'
            ORDER BY g.name
        """)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if exclude_ids and not steam_app_id:
        rows = [r for r in rows if r["app_id"] not in exclude_ids]

    if limit and not steam_app_id:
        rows = rows[:limit]

    return rows


def fetch_community_reports(steam_app_id: int) -> list[dict]:
    """Fetch reports from ProtonDB Community API."""
    url = f"{COMMUNITY_API}/games/{steam_app_id}/reports"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return data
        return []
    except Exception as e:
        print(f"  [WARN] Community API error for {steam_app_id}: {e}")
        return []


def fetch_official_summary(steam_app_id: int) -> dict | None:
    """Fetch tier summary from official ProtonDB API."""
    url = f"{OFFICIAL_API}/{steam_app_id}.json"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def extract_env_vars(text: str) -> dict:
    """Extract environment variables from report text."""
    matches = ENV_VAR_PATTERN.findall(text)
    env_vars = {}
    for key, value in matches:
        key = key.upper()
        if key not in ("COMMAND",):
            env_vars[key] = value
    return env_vars


def extract_launch_options(text: str) -> str | None:
    """Extract launch option strings from report text."""
    match = LAUNCH_OPT_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    return None


def extract_proton_version(text: str, report_proton: str | None = None) -> str | None:
    """Extract Proton version from report text or field."""
    if report_proton and report_proton not in ("Default", "default", "None", "none", ""):
        return report_proton

    match = PROTON_VER_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    return None


def analyze_reports(reports: list[dict], game_name: str) -> dict:
    """Analyze multiple reports and extract the most useful config data."""
    if not reports:
        return {}

    # Sort by timestamp (newest first)
    reports.sort(key=lambda r: r.get("timestamp", 0), reverse=True)

    all_env_vars = {}
    all_launch_opts = []
    all_proton_versions = []
    ratings = []
    configs = []

    for report in reports[:20]:  # analyze up to 20 most recent reports
        notes = report.get("notes", "") or ""
        rating = report.get("rating", "")
        proton = report.get("protonVersion", "")
        specs = report.get("specs", "") or ""
        os_info = report.get("os", "") or ""
        gpu_driver = report.get("gpuDriver", "") or ""
        timestamp = report.get("timestamp", 0)

        if rating:
            ratings.append(rating.lower())

        # Extract env vars from notes
        env_vars = extract_env_vars(notes)
        if env_vars:
            all_env_vars.update(env_vars)

        # Extract launch options from notes
        launch_opt = extract_launch_options(notes)
        if launch_opt:
            all_launch_opts.append(launch_opt)

        # Extract proton version
        pv = extract_proton_version(notes, proton)
        if pv:
            all_proton_versions.append(pv)

        # Save full config for attribution
        if notes.strip() and (env_vars or launch_opt or rating.lower() in ("platinum", "gold")):
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d") if timestamp else "unknown"
            configs.append({
                "date": dt,
                "rating": rating,
                "proton": proton,
                "os": os_info,
                "gpu_driver": gpu_driver,
                "specs": specs,
                "notes": notes[:500],
                "env_vars": env_vars,
                "launch_options": launch_opt,
                "source": f"ProtonDB report ({dt})",
            })

    result = {
        "report_count": len(reports),
        "analyzed": min(len(reports), 20),
    }

    if all_env_vars:
        result["env_vars"] = all_env_vars

    if all_launch_opts:
        # Pick the most complete launch option
        best = max(all_launch_opts, key=len)
        result["launch_options"] = best

    if all_proton_versions:
        # Pick the most common proton version
        from collections import Counter
        pv_counts = Counter(all_proton_versions)
        result["proton_version"] = pv_counts.most_common(1)[0][0]

    if ratings:
        from collections import Counter
        rating_counts = Counter(ratings)
        result["dominant_rating"] = rating_counts.most_common(1)[0][0]

    if configs:
        result["top_configs"] = configs[:5]  # Keep top 5 configs

    return result


def find_steam_app_id(game_name: str) -> int | None:
    """Try to find Steam app ID by searching DuckDuckGo."""
    try:
        from ddgs import DDGS
        results = DDGS().text(f"site:store.steampowered.com {game_name}", max_results=3)
        for r in results:
            url = r.get("href", "")
            match = re.search(r"store\.steampowered\.com/app/(\d+)", url)
            if match:
                return int(match.group(1))
    except Exception:
        pass
    return None


def save_protondb_data(results: list[dict]) -> None:
    """Save ProtonDB report analysis to manual JSON files."""
    cmd_file = MANUAL_DIR / "linux_commands.json"
    cmd_data = json.loads(cmd_file.read_text(encoding="utf-8")) if cmd_file.exists() else {"games": []}
    links_file = MANUAL_DIR / "useful_links.json"
    links_data = json.loads(links_file.read_text(encoding="utf-8")) if links_file.exists() else {"links": []}

    # Index existing entries by name (lowercase) for dedup
    existing = {}
    for g in cmd_data.get("games", []):
        existing[g.get("name", "").strip().lower()] = g

    # Index existing links by (name, url) to avoid duplicates
    existing_links = set()
    for link in links_data.get("links", []):
        key = (link.get("name", "").strip().lower(), link.get("url", ""))
        existing_links.add(key)

    updated = 0
    links_added = 0
    for r in results:
        name_lower = r.get("name", "").strip().lower()
        if not name_lower:
            continue

        steam_id = r.get("steam_app_id")
        analysis = r.get("analysis", {})
        if not analysis:
            continue

        if name_lower in existing:
            # Merge new data into existing entry
            entry = existing[name_lower]
            if analysis.get("env_vars") and not entry.get("env_vars"):
                entry["env_vars"] = analysis["env_vars"]
            if analysis.get("launch_options") and not entry.get("launch_options"):
                entry["launch_options"] = analysis["launch_options"]
            if analysis.get("proton_version") and not entry.get("proton_version"):
                entry["proton_version"] = analysis["proton_version"]
            if analysis.get("dominant_rating") and not entry.get("protondb_tier"):
                entry["protondb_tier"] = analysis["dominant_rating"]
            if analysis.get("top_configs"):
                entry["protondb_configs"] = analysis["top_configs"]
            updated += 1
        else:
            # New entry
            new_entry = {
                "app_id": steam_id or r.get("app_id"),
                "name": r.get("name"),
                "launch_options": analysis.get("launch_options"),
                "env_vars": analysis.get("env_vars", {}),
                "proton_version": analysis.get("proton_version"),
                "protondb_tier": analysis.get("dominant_rating"),
                "linux_status": "works" if analysis.get("dominant_rating") in ("platinum", "gold") else "check",
            }
            if analysis.get("top_configs"):
                new_entry["protondb_configs"] = analysis["top_configs"]
            cmd_data["games"].append(new_entry)
            updated += 1

        # Add direct ProtonDB link for games where we found the Steam app ID
        if steam_id:
            pdb_url = f"https://www.protondb.com/app/{steam_id}"
            link_key = (name_lower, pdb_url)
            if link_key not in existing_links:
                report_count = analysis.get("report_count", 0)
                tier = analysis.get("official_tier", analysis.get("dominant_rating", ""))
                tier_str = f" ({tier})" if tier else ""
                links_data["links"].append({
                    "app_id": r.get("app_id"),
                    "name": r.get("name"),
                    "url": pdb_url,
                    "title_en": f"ProtonDB reports{tier_str} — {report_count} reports",
                    "title_es": f"Reportes ProtonDB{tier_str} — {report_count} reportes",
                    "source": "protondb",
                    "link_type": "guide",
                })
                existing_links.add(link_key)
                links_added += 1

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    cmd_data["last_updated"] = today
    links_data["last_updated"] = today
    cmd_file.write_text(json.dumps(cmd_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    links_file.write_text(json.dumps(links_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[OK] Updated {updated} entries in linux_commands.json")
    print(f"[OK] Added {links_added} ProtonDB direct links to useful_links.json")


def fetch_for_ids(db_path: Path, app_ids: list[int]) -> int:
    """Fetch ProtonDB data for specific app_ids and upsert directly into DB.

    Writes to linux_compat (tier, proton_version, launch_options, env_vars)
    and useful_links (ProtonDB page link).
    Returns number of games successfully processed.
    """
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Only process games that exist and are type 'game' with positive IDs.
    placeholders = ",".join("?" * len(app_ids))
    cur.execute(
        f"SELECT app_id, name FROM games WHERE app_id IN ({placeholders}) "
        f"AND app_id > 0 AND type = 'game'",
        app_ids,
    )
    games = cur.fetchall()

    if not games:
        conn.close()
        return 0

    print(f"[ProtonDB] Processing {len(games)}/{len(app_ids)} eligible games")

    success = 0
    for i, (app_id, name) in enumerate(games, 1):
        try:
            reports = fetch_community_reports(app_id)
            summary = fetch_official_summary(app_id)

            if not reports and not summary:
                time.sleep(REQUEST_DELAY)
                continue

            analysis = analyze_reports(reports, name)

            if summary and summary.get("tier"):
                if not analysis.get("dominant_rating"):
                    analysis["dominant_rating"] = summary["tier"]
                analysis["official_tier"] = summary["tier"]

            _upsert_protondb_to_db(cur, app_id, analysis)
            success += 1

        except Exception as exc:
            print(f"  [WARN] ProtonDB {app_id} ({name}): {exc}")

        if i % 50 == 0:
            conn.commit()
            print(f"  [ProtonDB] Progress: {i}/{len(games)} ({success} ok)")

        time.sleep(REQUEST_DELAY)

    conn.commit()
    conn.close()
    print(f"[ProtonDB] Done: {success}/{len(games)} games enriched")
    return success


def _upsert_protondb_to_db(cur: sqlite3.Cursor, app_id: int,
                           analysis: dict) -> None:
    """Write ProtonDB analysis results into the database using an existing cursor."""
    tier = analysis.get("dominant_rating") or analysis.get("official_tier")
    proton_ver = analysis.get("proton_version")
    launch_opts = analysis.get("launch_options")
    env_vars = analysis.get("env_vars")
    env_json = json.dumps(env_vars) if env_vars else None

    linux_status = None
    if tier in ("platinum", "gold"):
        linux_status = "works"

    cur.execute(
        """INSERT INTO linux_compat (app_id, protondb_tier, proton_version,
               launch_options, env_vars, linux_status)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(app_id) DO UPDATE SET
               protondb_tier = COALESCE(excluded.protondb_tier, linux_compat.protondb_tier),
               proton_version = COALESCE(
                   CASE WHEN linux_compat.proton_version IS NULL
                             OR linux_compat.proton_version LIKE '%Check%'
                        THEN excluded.proton_version
                        ELSE linux_compat.proton_version END,
                   linux_compat.proton_version),
               launch_options = COALESCE(excluded.launch_options, linux_compat.launch_options),
               env_vars = COALESCE(excluded.env_vars, linux_compat.env_vars),
               linux_status = CASE
                   WHEN linux_compat.linux_status IN ('check', '') OR linux_compat.linux_status IS NULL
                   THEN COALESCE(excluded.linux_status, linux_compat.linux_status)
                   ELSE linux_compat.linux_status END""",
        (app_id, tier, proton_ver, launch_opts, env_json, linux_status),
    )

    # Add ProtonDB link.
    report_count = analysis.get("report_count", 0)
    official_tier = analysis.get("official_tier", tier or "")
    tier_str = f" ({official_tier})" if official_tier else ""
    pdb_url = f"https://www.protondb.com/app/{app_id}"

    cur.execute(
        """INSERT OR IGNORE INTO useful_links
               (app_id, url, title_en, title_es, source, link_type)
           VALUES (?, ?, ?, ?, 'protondb', 'guide')""",
        (
            app_id,
            pdb_url,
            f"ProtonDB reports{tier_str} — {report_count} reports",
            f"Reportes ProtonDB{tier_str} — {report_count} reportes",
        ),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Fetch ProtonDB reports and extract launch configs"
    )
    parser.add_argument("--app-id", type=int, help="Steam App ID to fetch")
    parser.add_argument("--limit", type=int, help="Max games to process")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fetched")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY)
    parser.add_argument("--reset-progress", action="store_true",
                        help="Delete progress file and re-process everything")
    parser.add_argument("--retry-failed", action="store_true",
                        help="Only re-try games that failed in previous runs")
    args = parser.parse_args()

    if not DB_FILE.exists():
        print(f"[ERROR] Database not found: {DB_FILE}")
        sys.exit(1)

    # --- Progress tracking ---
    if args.reset_progress:
        if PROGRESS_FILE.exists():
            PROGRESS_FILE.unlink()
            print("[INFO] Progress file deleted.")

    succeeded_ids, failed_ids = load_progress()
    # Always persist progress file so CI commit step can find it
    save_progress(succeeded_ids, failed_ids)

    if args.retry_failed:
        if not failed_ids:
            print("[INFO] No failed games to retry.")
            return
        print(f"[INFO] Retrying {len(failed_ids)} previously failed games...")
        # Get all games, then filter to only failed ones
        games = get_games_from_db(DB_FILE, steam_app_id=args.app_id,
                                  limit=args.limit)
        games = [g for g in games if g["app_id"] in failed_ids]
        # Remove them from failed so they get re-classified
        failed_ids -= {g["app_id"] for g in games}
    else:
        skip_ids = succeeded_ids | failed_ids if not args.app_id else None
        if skip_ids:
            print(f"[INFO] Skipping {len(succeeded_ids)} succeeded, "
                  f"{len(failed_ids)} failed from previous runs.")
        games = get_games_from_db(DB_FILE, steam_app_id=args.app_id,
                                  limit=args.limit, exclude_ids=skip_ids)

    if not games:
        print("[INFO] No games to process.")
        return

    print(f"LinuxPlayDB -- ProtonDB Report Fetcher ({len(games)} games)")
    print(f"Sources: Community API ({COMMUNITY_API}) + Official API\n")

    if args.dry_run:
        for g in games:
            print(f"  [{g['app_id']}] {g['name']}")
        return

    results = []
    success = 0
    no_reports = 0
    errors = 0

    for i, game in enumerate(games, 1):
        try:
            print(f"[{i}/{len(games)}] {game['name']}...", end=" ", flush=True)

            # Try to find real Steam app ID (our DB uses negative IDs from seed)
            steam_id = game["app_id"] if game["app_id"] > 0 else None

            if not steam_id:
                steam_id = find_steam_app_id(game["name"])
                if steam_id:
                    print(f"(Steam: {steam_id})", end=" ", flush=True)

            if not steam_id:
                print("[SKIP] No Steam ID found")
                succeeded_ids.add(game["app_id"])
                save_progress(succeeded_ids, failed_ids)
                continue

            # Fetch community reports
            reports = fetch_community_reports(steam_id)

            # Fetch official summary
            summary = fetch_official_summary(steam_id)

            if not reports and not summary:
                print("[EMPTY] No data")
                no_reports += 1
                succeeded_ids.add(game["app_id"])
                save_progress(succeeded_ids, failed_ids)
                time.sleep(args.delay)
                continue

            # Analyze reports
            analysis = analyze_reports(reports, game["name"])

            # Merge official summary tier
            if summary and summary.get("tier"):
                if not analysis.get("dominant_rating"):
                    analysis["dominant_rating"] = summary["tier"]
                analysis["official_tier"] = summary["tier"]
                analysis["official_confidence"] = summary.get("confidence", "")

            report_count = analysis.get("report_count", 0)
            tier = analysis.get("dominant_rating", "?")
            env_count = len(analysis.get("env_vars", {}))
            config_count = len(analysis.get("top_configs", []))

            print(f"[OK] {report_count} reports | tier: {tier} | "
                  f"envs: {env_count} | configs: {config_count}")

            results.append({
                "app_id": game["app_id"],
                "steam_app_id": steam_id,
                "name": game["name"],
                "analysis": analysis,
            })
            success += 1
            succeeded_ids.add(game["app_id"])

        except Exception as exc:
            print(f"[ERROR] {exc}")
            failed_ids.add(game["app_id"])
            errors += 1

        save_progress(succeeded_ids, failed_ids)

        # Checkpoint: save partial results every N games to avoid data loss
        if results and len(results) % CHECKPOINT_INTERVAL == 0:
            print(f"\n[CHECKPOINT] Saving {len(results)} results so far...")
            save_protondb_data(results)

        if i < len(games):
            time.sleep(args.delay)

    # Save results
    if results:
        save_protondb_data(results)

        # Save full output for reference
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_file = OUTPUT_DIR / f"protondb_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        output_file.write_text(
            json.dumps(results, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[OK] Full output: {output_file}")

    print(f"\nDone! Success: {success}, No reports: {no_reports}, "
          f"Errors: {errors}, Total: {len(games)}")


if __name__ == "__main__":
    main()
