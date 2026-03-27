#!/usr/bin/env python3
"""Research game compatibility using Mistral AI + DuckDuckGo search.

Uses Mistral's free API (1B tokens/month) with DuckDuckGo web search to find
AMD RT/PT compatibility, rt_type overrides, and useful links.

Launch options, env vars, and proton versions are handled by fetch_protondb_reports.py.

Requirements:
    pip install mistralai ddgs requests

Usage:
    export MISTRAL_API_KEY="your-api-key-here"
    python research_with_ai.py                    # Research all games missing data
    python research_with_ai.py --app-id -646526   # Research a specific game
    python research_with_ai.py --limit 50         # Research first 50 games
    python research_with_ai.py --dry-run           # Show what would be researched
"""

import argparse
import json
import os
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from mistralai import Mistral
except ImportError:
    if __name__ == "__main__":
        print("[ERROR] mistralai not installed. Run: pip install mistralai")
        sys.exit(1)
    raise

try:
    from ddgs import DDGS
except ImportError:
    if __name__ == "__main__":
        print("[ERROR] ddgs not installed. Run: pip install ddgs")
        sys.exit(1)
    raise

ROOT = Path(__file__).parent.parent
DB_FILE = ROOT / "data" / "linuxplaydb.db"
MANUAL_DIR = ROOT / "scripts" / "manual"
OUTPUT_DIR = ROOT / "scripts" / "research_output"

# Mistral free tier: 1B tokens/month, 2 RPM for small models.
# mistral-small-latest (Small 3.1, 24B) — good structured JSON extraction.
# Retry with backoff handles the 2 RPM rate limit naturally.
MISTRAL_MODEL = "mistral-small-latest"
REQUEST_DELAY = 5  # seconds between Mistral calls (backoff handles rate limits)
SEARCH_DELAY = 3.0   # seconds between DuckDuckGo searches (avoid IP blocks in CI)
PROGRESS_FILE = Path(__file__).parent / "research_output" / "progress.json"

ANALYSIS_PROMPT = """You are a gaming compatibility researcher for LinuxPlayDB.

Analyze the following web search results about the game **{name}** and extract structured compatibility data.

## SEARCH RESULTS:
{search_results}

## EXTRACT THE FOLLOWING:

1. **AMD GPU Ray Tracing compatibility** — classify as ONE of:
   - "amd_ok" = RT and/or PT works correctly on AMD RDNA2+ GPUs
   - "amd_pt" = Path tracing works on AMD but standard RT has issues
   - "amd_rt_only" = Ray tracing works but path tracing does NOT on AMD
   - "nvidia_only" = RT/PT only works on NVIDIA (OptiX, RTX Remix, NVIDIA-exclusive extensions), crashes or broken on AMD
   - "unknown" = Not enough information in the search results

   IMPORTANT classification notes:
   - Games with custom/proprietary path tracing engines (voxel-based, software GI, etc.) that work on ALL GPUs should be "amd_ok"
   - Games using RTX Remix, OptiX, or NVIDIA-specific Vulkan RT extensions are "nvidia_only"
   - If a game has path tracing that works independently of DXR/Vulkan RT hardware (e.g. Teardown, voxel engines), it's "amd_ok"

2. **Useful links** — extract REAL URLs from the search results that help with Linux/AMD gaming.

RESPOND ONLY with valid JSON (no markdown fences, no explanation, ONLY the JSON object):

{{
  "app_id": {app_id},
  "name": "{name}",
  "amd_status": "amd_ok|amd_pt|amd_rt_only|nvidia_only|unknown",
  "rt_type_override": null,
  "amd_notes_en": "Brief explanation of AMD RT status based on search results",
  "amd_notes_es": "Breve explicacion del estado AMD RT",
  "useful_links": [
    {{
      "url": "https://actual-url-from-search-results",
      "title_en": "Link title in English",
      "title_es": "Titulo del link en espanol",
      "source": "protondb|pcgamingwiki|reddit|github|steam",
      "link_type": "fix|guide|discussion|wiki|video"
    }}
  ],
  "confidence": "high|medium|low",
  "research_date": "{date}"
}}

IMPORTANT:
- Only include information actually present in the search results. Do NOT fabricate data.
- If search results don't mention AMD RT, set amd_status to "unknown".
- useful_links MUST be real URLs from the search results above. Do not invent URLs.
- Set confidence based on how much relevant information was found.
- Do NOT extract ProtonDB tier, anti-cheat, native Linux status, launch options, or env vars — we get those from dedicated APIs.
- rt_type_override: Set to "pt" if search results confirm the game uses path tracing, global illumination via ray tracing, or voxel-based lighting (even if not DXR/RTX). Set to "rt" if it only has standard ray tracing (reflections, shadows). Leave null ONLY if no RT/PT info found.
- Many games have path tracing via custom engines (Teardown voxel PT, Minecraft Java shaders, Lumen GI). These MUST get rt_type_override = "pt" because the NVIDIA database does not list them.
"""


def load_progress() -> tuple[set[int], set[int]]:
    """Load sets of succeeded and failed app_ids from progress file.

    Returns (succeeded_ids, failed_ids).
    """
    if PROGRESS_FILE.exists():
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            # Backwards compat: old format had "researched_ids" as a flat list
            if "succeeded_ids" in data:
                return (set(data.get("succeeded_ids", [])),
                        set(data.get("failed_ids", [])))
            return set(data.get("researched_ids", [])), set()
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


def get_games_to_research(db_path: Path, app_id: int | None = None,
                          limit: int | None = None,
                          exclude_ids: set[int] | None = None) -> list[dict]:
    """Get games from DB that need research."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    if app_id:
        cur.execute(
            "SELECT g.app_id, g.name FROM games g WHERE g.app_id = ?",
            (app_id,),
        )
    else:
        # Games with graphics features (RT/PT/DLSS/FSR) that lack research data
        cur.execute("""
            SELECT g.app_id, g.name
            FROM games g
            JOIN graphics_features gf ON g.app_id = gf.app_id
            LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
            WHERE g.type = 'game'
              AND (gf.rt_type IN ('rt', 'pt')
                   OR gf.dlss_sr = 1 OR gf.fsr3 = 1 OR gf.fsr4 = 1)
              AND lc.launch_options IS NULL
            ORDER BY g.name
        """)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    # Filter out already-researched games
    if exclude_ids and not app_id:
        rows = [r for r in rows if r["app_id"] not in exclude_ids]

    if limit and not app_id:
        rows = rows[:limit]

    return rows


def _search_with_retry(query: str, max_results: int = 5,
                       max_retries: int = 3) -> list[dict]:
    """Execute a single DDGS search with exponential backoff on failure."""
    for attempt in range(max_retries):
        try:
            return DDGS().text(query, max_results=max_results, backend="auto")
        except Exception as e:
            if attempt < max_retries - 1:
                wait = (2 ** attempt) + random.uniform(0.5, 2.0)
                print(f"  [RETRY] Search attempt {attempt + 1} failed: {e}. "
                      f"Waiting {wait:.1f}s...")
                time.sleep(wait)
            else:
                print(f"  [WARN] Search failed after {max_retries} attempts for "
                      f"'{query}': {e}")
                return []


def search_game(game_name: str) -> str:
    """Search DuckDuckGo for game compatibility info. Returns formatted results."""
    queries = [
        f"{game_name} AMD ray tracing path tracing RDNA compatibility",
        f"{game_name} Steam Linux Proton launch options env vars fix",
        f"{game_name} ray tracing path tracing voxel global illumination engine GPU",
    ]

    all_results = []
    seen_urls = set()

    for query in queries:
        results = _search_with_retry(query)
        for r in results:
            url = r.get("href", "")
            if url not in seen_urls:
                seen_urls.add(url)
                all_results.append(r)
        time.sleep(SEARCH_DELAY)

    if not all_results:
        return ""

    # Format results for the LLM
    formatted = []
    for i, r in enumerate(all_results, 1):
        formatted.append(
            f"[{i}] {r.get('title', 'No title')}\n"
            f"    URL: {r.get('href', '')}\n"
            f"    {r.get('body', '')}"
        )

    return "\n\n".join(formatted)


def research_game(client: Mistral, game: dict, max_retries: int = 3) -> dict | None:
    """Search web + analyze with Mistral to research a single game."""
    # Step 1: Search the web
    search_results = search_game(game["name"])

    if not search_results:
        print(f"  [WARN] No search results for {game['name']}")
        return None

    # Step 2: Analyze with Mistral
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = ANALYSIS_PROMPT.format(
        name=game["name"],
        app_id=game["app_id"],
        search_results=search_results,
        date=today,
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.complete(
                model=MISTRAL_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=2000,
            )

            text = response.choices[0].message.content.strip()

            # Clean markdown fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            return data

        except json.JSONDecodeError as e:
            print(f"  [WARN] Invalid JSON for {game['name']}: {e}")
            raw_dir = OUTPUT_DIR / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            raw_file = raw_dir / f"{game['app_id']}_raw.txt"
            raw_file.write_text(text, encoding="utf-8")
            print(f"  [WARN] Raw response saved to {raw_file}")
            return None

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "rate" in err_str.lower():
                wait = min(30 * (2 ** (attempt - 1)), 120) + random.uniform(1, 5)
                if attempt < max_retries:
                    print(f"  [WAIT] Rate limited. Waiting {wait:.0f}s... (attempt {attempt}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  [SKIP] Rate limited after {max_retries} retries.")
                    return None
            else:
                print(f"  [ERROR] API error for {game['name']}: {e}")
                return None

    return None


# ── Post-LLM Validation ──────────────────────────────────────────────


def validate_result(data: dict) -> dict:
    """Sanitize a single Mistral result, fixing or removing bad data.

    Returns the cleaned dict. Logs every correction so we can audit.
    """
    name = data.get("name", "?")
    fixes = []

    # ── notes ─────────────────────────────────────────────────────
    for field in ("amd_notes_en", "amd_notes_es"):
        note = data.get(field, "")
        if not note:
            continue
        # Reject if it reads like a personal blog post / rant
        if any(phrase in note.lower() for phrase in
               ("f you microsoft", "i kept reading", "i bit the bullet",
                "i'm running it under bottles")):
            data[field] = ""
            fixes.append(f"{field}: removed personal anecdote")

    # ── confidence gating ─────────────────────────────────────────
    if data.get("confidence") == "low":
        # Low confidence = don't trust the AMD classification
        if data.get("amd_status") and data["amd_status"] != "unknown":
            fixes.append(f"low confidence: downgraded amd_status from {data['amd_status']} to unknown")
            data["amd_status"] = "unknown"

    if fixes:
        print(f"  [CLEAN] {name}: {len(fixes)} fixes applied")
        for f in fixes:
            print(f"    - {f}")

    return data


def save_results(results: list[dict]) -> None:
    """Save research results into the manual JSON files (amd_specific + useful_links)."""
    amd_file = MANUAL_DIR / "amd_specific.json"
    links_file = MANUAL_DIR / "useful_links.json"

    amd_data = json.loads(amd_file.read_text(encoding="utf-8")) if amd_file.exists() else {"games": []}
    links_data = json.loads(links_file.read_text(encoding="utf-8")) if links_file.exists() else {"links": []}

    # Index existing entries by app_id for dedup
    amd_index = {g["app_id"] for g in amd_data.get("games", [])}
    link_index = {(l["app_id"], l["url"]) for l in links_data.get("links", [])}

    for r in results:
        app_id = r.get("app_id")
        if not app_id:
            continue

        # AMD data
        if r.get("amd_status") and r["amd_status"] != "unknown" and app_id not in amd_index:
            entry = {
                "app_id": app_id,
                "name": r.get("name", ""),
                "amd_status": r["amd_status"],
                "notes_en": r.get("amd_notes_en", ""),
                "notes_es": r.get("amd_notes_es", ""),
            }
            if r.get("rt_type_override"):
                entry["rt_type"] = r["rt_type_override"]
            amd_data["games"].append(entry)
            amd_index.add(app_id)

        # Useful links
        for link in r.get("useful_links", []):
            url = link.get("url", "")
            if url and (app_id, url) not in link_index:
                links_data["links"].append({
                    "app_id": app_id,
                    "url": url,
                    "title_en": link.get("title_en", ""),
                    "title_es": link.get("title_es", ""),
                    "source": link.get("source", ""),
                    "link_type": link.get("link_type", ""),
                })
                link_index.add((app_id, url))

    # Update timestamps
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    amd_data["last_updated"] = today
    links_data["last_updated"] = today

    # Write back
    amd_file.write_text(json.dumps(amd_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    links_file.write_text(json.dumps(links_data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"\n[OK] Saved: {len(amd_data['games'])} AMD entries, "
          f"{len(links_data['links'])} useful links")


def save_full_research(results: list[dict]) -> None:
    """Save complete research results to a separate file for reference."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"research_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(
        json.dumps(results, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"[OK] Full research saved to {output_file}")


def research_for_ids(db_path: Path, app_ids: list[int]) -> int:
    """Research specific app_ids with AI and upsert results directly into DB.

    Only researches games that have RT/PT features (same filter as the main
    research flow). Returns the number of successfully researched games.
    """
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        print("[AI Research] No MISTRAL_API_KEY — skipping")
        return 0

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # Count total RT/PT games in batch for skip reporting.
    placeholders = ",".join("?" * len(app_ids))
    cur.execute(
        f"""SELECT COUNT(*)
            FROM games g
            JOIN graphics_features gf ON g.app_id = gf.app_id
            WHERE g.app_id IN ({placeholders})
              AND g.type = 'game'
              AND (gf.rt_type IN ('rt', 'pt')
                   OR gf.dlss_sr = 1 OR gf.fsr3 = 1 OR gf.fsr4 = 1)""",
        app_ids,
    )
    total_eligible = cur.fetchone()[0]

    # Only research games that need it: never researched, research failed,
    # 10+ new ProtonDB reports, or ProtonDB tier changed.
    cur.execute(
        f"""SELECT g.app_id, g.name
            FROM games g
            JOIN graphics_features gf ON g.app_id = gf.app_id
            LEFT JOIN research_snapshots rs ON g.app_id = rs.app_id
            WHERE g.app_id IN ({placeholders})
              AND g.type = 'game'
              AND (gf.rt_type IN ('rt', 'pt')
                   OR gf.dlss_sr = 1 OR gf.fsr3 = 1 OR gf.fsr4 = 1)
              AND (
                  rs.ai_researched_at IS NULL
                  OR gf.amd_status IS NULL
                  OR (rs.protondb_total IS NOT NULL
                      AND rs.protondb_total_at_research IS NOT NULL
                      AND rs.protondb_total - rs.protondb_total_at_research >= 10)
                  OR (rs.protondb_tier IS NOT NULL
                      AND rs.protondb_tier_at_research IS NOT NULL
                      AND rs.protondb_tier != rs.protondb_tier_at_research)
              )""",
        app_ids,
    )
    games = [dict(r) for r in cur.fetchall()]

    skipped = total_eligible - len(games)
    if skipped > 0:
        print(f"[AI Research] Skipped {skipped}/{total_eligible} games "
              f"(no new ProtonDB data since last research)")

    if not games:
        conn.close()
        print("[AI Research] No eligible games in batch")
        return 0

    print(f"[AI Research] Researching {len(games)} games")

    client = Mistral(api_key=api_key)
    # Switch to a plain cursor for upserts.
    conn.row_factory = None
    cur = conn.cursor()
    success = 0

    for i, game in enumerate(games, 1):
        print(f"  [{i}/{len(games)}] {game['name']}...", end=" ", flush=True)

        data = research_game(client, game)
        if data:
            data = validate_result(data)
            _upsert_research_to_db(cur, game["app_id"], data)
            _update_research_snapshot(cur, game["app_id"])
            confidence = data.get("confidence", "?")
            amd = data.get("amd_status", "?")
            print(f"AMD: {amd} | Confidence: {confidence}")
            success += 1
        else:
            print("[SKIP]")

        if i % 10 == 0:
            conn.commit()

        if i < len(games):
            time.sleep(REQUEST_DELAY)

    conn.commit()
    conn.close()
    print(f"[AI Research] Done: {success}/{len(games)} researched")
    return success


def _upsert_research_to_db(cur: sqlite3.Cursor, app_id: int,
                           data: dict) -> None:
    """Write AI research results into the database using an existing cursor."""
    amd_status = data.get("amd_status")
    rt_override = data.get("rt_type_override")
    notes_en = data.get("amd_notes_en", "")
    notes_es = data.get("amd_notes_es", "")

    if amd_status and amd_status != "unknown":
        if rt_override:
            cur.execute(
                """UPDATE graphics_features
                   SET amd_status = ?,
                       rt_type = CASE WHEN ? IS NOT NULL THEN ? ELSE rt_type END,
                       notes_en = COALESCE(?, notes_en),
                       notes_es = COALESCE(?, notes_es)
                   WHERE app_id = ?""",
                (amd_status, rt_override, rt_override, notes_en or None,
                 notes_es or None, app_id),
            )
        else:
            cur.execute(
                """UPDATE graphics_features
                   SET amd_status = ?,
                       notes_en = COALESCE(?, notes_en),
                       notes_es = COALESCE(?, notes_es)
                   WHERE app_id = ?""",
                (amd_status, notes_en or None, notes_es or None, app_id),
            )

    # Upsert useful links.
    for link in data.get("useful_links", []):
        url = link.get("url", "")
        if not url:
            continue
        cur.execute(
            """INSERT OR IGNORE INTO useful_links
                   (app_id, url, title_en, title_es, source, link_type)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                app_id,
                url,
                link.get("title_en", ""),
                link.get("title_es", ""),
                link.get("source", ""),
                link.get("link_type", ""),
            ),
        )


def _update_research_snapshot(cur: sqlite3.Cursor, app_id: int) -> None:
    """Mark a game as researched and snapshot the current ProtonDB state."""
    now = datetime.now(timezone.utc).isoformat()
    cur.execute(
        """INSERT INTO research_snapshots (app_id, ai_researched_at,
               protondb_total_at_research, protondb_tier_at_research)
           VALUES (?, ?, NULL, NULL)
           ON CONFLICT(app_id) DO UPDATE SET
               ai_researched_at = excluded.ai_researched_at,
               protondb_total_at_research = research_snapshots.protondb_total,
               protondb_tier_at_research = research_snapshots.protondb_tier""",
        (app_id, now),
    )


def main():
    parser = argparse.ArgumentParser(
        description="Research game compatibility using Mistral AI + DuckDuckGo search"
    )
    parser.add_argument("--app-id", type=int, help="Research a specific game by internal App ID")
    parser.add_argument("--limit", type=int, help="Maximum number of games to research")
    parser.add_argument("--dry-run", action="store_true", help="Show games to research without calling APIs")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help=f"Seconds between Mistral calls (default: {REQUEST_DELAY})")
    parser.add_argument("--reset-progress", action="store_true", help="Reset progress tracking (re-research all games)")
    parser.add_argument("--retry-failed", action="store_true", help="Retry only previously failed games")
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key and not args.dry_run:
        print("[ERROR] MISTRAL_API_KEY environment variable not set.")
        print("Get your free key at: https://console.mistral.ai/api-keys/")
        sys.exit(1)

    # Check database
    if not DB_FILE.exists():
        print(f"[ERROR] Database not found: {DB_FILE}")
        print("Run 'python build_db.py' first.")
        sys.exit(1)

    # Progress tracking
    if args.reset_progress and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("[OK] Progress reset.")

    if args.app_id:
        succeeded, failed_ids = set(), set()
    else:
        succeeded, failed_ids = load_progress()

    if args.retry_failed:
        # Only retry previously failed games
        if not failed_ids:
            print("[INFO] No failed games to retry.")
            return
        print(f"[INFO] Retrying {len(failed_ids)} previously failed games.")
        exclude_ids = succeeded
    else:
        exclude_ids = succeeded | failed_ids
        if exclude_ids:
            print(f"[INFO] Skipping {len(succeeded)} succeeded, {len(failed_ids)} failed.")

    # Get games to research
    games = get_games_to_research(DB_FILE, app_id=args.app_id, limit=args.limit,
                                  exclude_ids=exclude_ids)

    if not games:
        print("[INFO] No games need research.")
        return

    est_time = len(games) * (args.delay + SEARCH_DELAY * 3 + 2)  # rough estimate
    print(f"LinuxPlayDB — AI Research ({len(games)} games)")
    print(f"Search: DuckDuckGo (free, no API key)")
    print(f"Analysis: Mistral {MISTRAL_MODEL} (1B tokens/month free)")
    print(f"Estimated time: ~{est_time / 60:.0f} minutes\n")

    if args.dry_run:
        print("Games to research:")
        for g in games:
            print(f"  [{g['app_id']}] {g['name']}")
        print(f"\nTotal: {len(games)} games")
        return

    # Initialize Mistral client
    client = Mistral(api_key=api_key)

    results = []
    success = 0
    failed = 0

    for i, game in enumerate(games, 1):
        print(f"[{i}/{len(games)}] Researching: {game['name']} ({game['app_id']})...")

        data = research_game(client, game)

        if data:
            data = validate_result(data)
            results.append(data)
            succeeded.add(game["app_id"])
            failed_ids.discard(game["app_id"])  # remove from failed if retrying
            confidence = data.get("confidence", "?")
            amd = data.get("amd_status", "?")
            links_count = len(data.get("useful_links", []))
            print(f"  [OK] AMD: {amd} | Links: {links_count} | Confidence: {confidence}")
            success += 1
        else:
            failed_ids.add(game["app_id"])
            failed += 1

        save_progress(succeeded, failed_ids)

        # Checkpoint results every 10 games
        if i % 10 == 0:
            if results:
                save_results(results)
                save_full_research(results)
            print(f"\n[CHECKPOINT] Saved {len(results)} results | "
                  f"{len(succeeded)} ok, {len(failed_ids)} failed.\n")

        # Rate limiting (skip on last item)
        if i < len(games):
            time.sleep(args.delay)

    # Final save
    save_progress(succeeded, failed_ids)
    if results:
        save_results(results)
        save_full_research(results)

    print(f"\nDone! Success: {success}, Failed: {failed}, Total: {len(games)}")
    print(f"Progress: {len(succeeded)} succeeded, {len(failed_ids)} failed across all sessions.")
    if failed_ids:
        print(f"Run with --retry-failed to retry the {len(failed_ids)} failed games.")


if __name__ == "__main__":
    main()
