#!/usr/bin/env python3
"""Research game compatibility using Groq (Llama 3.3) + DuckDuckGo search.

Uses Groq's free API (14,400 req/day) with DuckDuckGo web search to find
AMD RT compatibility, Linux workarounds, launch options, and useful links.

Requirements:
    pip install groq ddgs requests

Usage:
    export GROQ_API_KEY="your-api-key-here"
    python research_with_ai.py                    # Research all games missing data
    python research_with_ai.py --app-id -646526   # Research a specific game
    python research_with_ai.py --limit 50         # Research first 50 games
    python research_with_ai.py --dry-run           # Show what would be researched
"""

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

try:
    from groq import Groq
except ImportError:
    print("[ERROR] groq not installed. Run: pip install groq")
    sys.exit(1)

try:
    from ddgs import DDGS
except ImportError:
    print("[ERROR] ddgs not installed. Run: pip install ddgs")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
DB_FILE = ROOT / "data" / "linuxplaydb.db"
MANUAL_DIR = ROOT / "scripts" / "manual"
OUTPUT_DIR = ROOT / "scripts" / "research_output"

# Groq free tier: 14,400 req/day, 30 RPM for llama-3.3-70b
REQUEST_DELAY = 2.5  # seconds between Groq calls (safe margin for 30 RPM)
SEARCH_DELAY = 1.0   # seconds between DuckDuckGo searches

ANALYSIS_PROMPT = """You are a gaming compatibility researcher for LinuxPlayDB.

Analyze the following web search results about the game **{name}** and extract structured compatibility data.

## SEARCH RESULTS:
{search_results}

## EXTRACT THE FOLLOWING:

1. **AMD GPU Ray Tracing compatibility** — classify as ONE of:
   - "amd_ok" = RT and/or PT works correctly on AMD RDNA2+ GPUs
   - "amd_pt" = Path tracing works on AMD but standard RT has issues
   - "amd_rt_only" = Ray tracing works but path tracing does NOT on AMD
   - "nvidia_only" = RT/PT only works on NVIDIA, crashes or broken on AMD
   - "unknown" = Not enough information in the search results

2. **Linux launch options and environment variables** — any Steam launch options or env vars needed:
   - gamemoderun, mangohud, PROTON_*, VKD3D_*, DXVK_*, RADV_*, MESA_* variables
   - Proton version recommendations (GE-Proton, Proton Experimental, etc.)

3. **Linux status** — does it work on Proton? Native? ProtonDB rating? Anti-cheat?

4. **Useful links** — extract REAL URLs from the search results that help with Linux/AMD gaming.

RESPOND ONLY with valid JSON (no markdown fences, no explanation, ONLY the JSON object):

{{
  "app_id": {app_id},
  "name": "{name}",
  "amd_status": "amd_ok|amd_pt|amd_rt_only|nvidia_only|unknown",
  "amd_notes_en": "Brief explanation of AMD RT status based on search results",
  "amd_notes_es": "Breve explicación del estado AMD RT",
  "linux_status": "works|cmd|broken|check|unknown",
  "launch_options": null,
  "env_vars": {{}},
  "proton_version": null,
  "protondb_tier": "platinum|gold|silver|bronze|borked|unknown",
  "native_linux": false,
  "anticheat": null,
  "anticheat_linux": null,
  "linux_notes_en": "Brief Linux compatibility notes from search results",
  "linux_notes_es": "Breves notas de compatibilidad Linux",
  "useful_links": [
    {{
      "url": "https://actual-url-from-search-results",
      "title_en": "Link title in English",
      "title_es": "Título del link en español",
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
- If no launch options found, set launch_options to null and env_vars to {{}}.
- useful_links MUST be real URLs from the search results above. Do not invent URLs.
- Set confidence based on how much relevant information was found.
"""


def get_games_to_research(db_path: Path, app_id: int | None = None,
                          limit: int | None = None) -> list[dict]:
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
        # Games that lack launch_options (most useful missing data)
        cur.execute("""
            SELECT g.app_id, g.name
            FROM games g
            LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
            WHERE g.type = 'game'
              AND lc.launch_options IS NULL
            ORDER BY g.name
        """)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if limit and not app_id:
        rows = rows[:limit]

    return rows


def search_game(game_name: str) -> str:
    """Search DuckDuckGo for game compatibility info. Returns formatted results."""
    queries = [
        f"{game_name} ProtonDB Linux Proton compatibility",
        f"{game_name} AMD ray tracing RDNA Linux vkd3d",
        f"{game_name} Steam launch options Linux fix",
    ]

    all_results = []
    seen_urls = set()

    for query in queries:
        try:
            results = DDGS().text(query, max_results=5)
            for r in results:
                url = r.get("href", "")
                if url not in seen_urls:
                    seen_urls.add(url)
                    all_results.append(r)
        except Exception as e:
            print(f"  [WARN] Search failed for '{query}': {e}")
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


def research_game(client: Groq, game: dict, max_retries: int = 3) -> dict | None:
    """Search web + analyze with Groq to research a single game."""
    # Step 1: Search the web
    search_results = search_game(game["name"])

    if not search_results:
        print(f"  [WARN] No search results for {game['name']}")
        return None

    # Step 2: Analyze with Groq
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = ANALYSIS_PROMPT.format(
        name=game["name"],
        app_id=game["app_id"],
        search_results=search_results,
        date=today,
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
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
                wait = 30
                if attempt < max_retries:
                    print(f"  [WAIT] Rate limited. Waiting {wait}s... (attempt {attempt}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  [SKIP] Rate limited after {max_retries} retries.")
                    return None
            else:
                print(f"  [ERROR] API error for {game['name']}: {e}")
                return None

    return None


def save_results(results: list[dict]) -> None:
    """Save research results into the manual JSON files."""
    amd_file = MANUAL_DIR / "amd_specific.json"
    cmd_file = MANUAL_DIR / "linux_commands.json"
    links_file = MANUAL_DIR / "useful_links.json"

    amd_data = json.loads(amd_file.read_text()) if amd_file.exists() else {"games": []}
    cmd_data = json.loads(cmd_file.read_text()) if cmd_file.exists() else {"games": []}
    links_data = json.loads(links_file.read_text()) if links_file.exists() else {"links": []}

    # Index existing entries by app_id for dedup
    amd_index = {g["app_id"] for g in amd_data.get("games", [])}
    cmd_index = {g["app_id"] for g in cmd_data.get("games", [])}
    link_index = {(l["app_id"], l["url"]) for l in links_data.get("links", [])}

    for r in results:
        app_id = r.get("app_id")
        if not app_id:
            continue

        # AMD data
        if r.get("amd_status") and r["amd_status"] != "unknown" and app_id not in amd_index:
            amd_data["games"].append({
                "app_id": app_id,
                "name": r.get("name", ""),
                "amd_status": r["amd_status"],
                "notes_en": r.get("amd_notes_en", ""),
                "notes_es": r.get("amd_notes_es", ""),
            })
            amd_index.add(app_id)

        # Linux commands
        has_cmd = r.get("launch_options") or r.get("env_vars") or r.get("proton_version")
        if has_cmd and app_id not in cmd_index:
            cmd_data["games"].append({
                "app_id": app_id,
                "name": r.get("name", ""),
                "launch_options": r.get("launch_options"),
                "env_vars": r.get("env_vars") if r.get("env_vars") else {},
                "proton_version": r.get("proton_version"),
                "linux_status": r.get("linux_status"),
                "protondb_tier": r.get("protondb_tier"),
                "native_linux": r.get("native_linux", False),
                "anticheat": r.get("anticheat"),
                "anticheat_linux": r.get("anticheat_linux"),
                "notes_en": r.get("linux_notes_en", ""),
                "notes_es": r.get("linux_notes_es", ""),
            })
            cmd_index.add(app_id)

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
    cmd_data["last_updated"] = today
    links_data["last_updated"] = today

    # Write back
    amd_file.write_text(json.dumps(amd_data, indent=2, ensure_ascii=False) + "\n")
    cmd_file.write_text(json.dumps(cmd_data, indent=2, ensure_ascii=False) + "\n")
    links_file.write_text(json.dumps(links_data, indent=2, ensure_ascii=False) + "\n")

    print(f"\n[OK] Saved: {len(amd_data['games'])} AMD entries, "
          f"{len(cmd_data['games'])} Linux commands, "
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


def main():
    parser = argparse.ArgumentParser(
        description="Research game compatibility using Groq AI + DuckDuckGo search"
    )
    parser.add_argument("--app-id", type=int, help="Research a specific game by internal App ID")
    parser.add_argument("--limit", type=int, help="Maximum number of games to research")
    parser.add_argument("--dry-run", action="store_true", help="Show games to research without calling APIs")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help=f"Seconds between Groq calls (default: {REQUEST_DELAY})")
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key and not args.dry_run:
        print("[ERROR] GROQ_API_KEY environment variable not set.")
        print("Get your free key at: https://console.groq.com")
        sys.exit(1)

    # Check database
    if not DB_FILE.exists():
        print(f"[ERROR] Database not found: {DB_FILE}")
        print("Run 'python build_db.py' first.")
        sys.exit(1)

    # Get games to research
    games = get_games_to_research(DB_FILE, app_id=args.app_id, limit=args.limit)

    if not games:
        print("[INFO] No games need research.")
        return

    est_time = len(games) * (args.delay + SEARCH_DELAY * 3 + 2)  # rough estimate
    print(f"LinuxPlayDB — AI Research ({len(games)} games)")
    print(f"Search: DuckDuckGo (free, no API key)")
    print(f"Analysis: Groq Llama 3.3 70B (14,400 req/day free)")
    print(f"Estimated time: ~{est_time / 60:.0f} minutes\n")

    if args.dry_run:
        print("Games to research:")
        for g in games:
            print(f"  [{g['app_id']}] {g['name']}")
        print(f"\nTotal: {len(games)} games")
        return

    # Initialize Groq client
    client = Groq(api_key=api_key)

    results = []
    success = 0
    failed = 0

    for i, game in enumerate(games, 1):
        print(f"[{i}/{len(games)}] Researching: {game['name']} ({game['app_id']})...")

        data = research_game(client, game)

        if data:
            results.append(data)
            confidence = data.get("confidence", "?")
            amd = data.get("amd_status", "?")
            linux = data.get("linux_status", "?")
            links_count = len(data.get("useful_links", []))
            print(f"  [OK] AMD: {amd} | Linux: {linux} | Links: {links_count} | Confidence: {confidence}")
            success += 1
        else:
            failed += 1

        # Save periodically (every 25 games)
        if len(results) > 0 and len(results) % 25 == 0:
            save_results(results)
            save_full_research(results)
            print(f"\n[CHECKPOINT] Saved {len(results)} results so far.\n")

        # Rate limiting (skip on last item)
        if i < len(games):
            time.sleep(args.delay)

    # Final save
    if results:
        save_results(results)
        save_full_research(results)

    print(f"\nDone! Success: {success}, Failed: {failed}, Total: {len(games)}")


if __name__ == "__main__":
    main()
