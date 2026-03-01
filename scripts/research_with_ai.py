#!/usr/bin/env python3
"""Research game compatibility using Google Gemini API with Search Grounding.

Uses Gemini 2.0 Flash (free tier) to search the web for AMD RT compatibility,
Linux workarounds, launch options, and useful links for each game in the database.

Requirements:
    pip install google-genai

Usage:
    export GEMINI_API_KEY="your-api-key-here"
    python research_with_ai.py                    # Research all games missing data
    python research_with_ai.py --app-id 1091500   # Research a specific game
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
    from google import genai
    from google.genai import types
except ImportError:
    print("[ERROR] google-genai not installed. Run: pip install google-genai")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
DB_FILE = ROOT / "data" / "linuxplaydb.db"
MANUAL_DIR = ROOT / "scripts" / "manual"
OUTPUT_DIR = ROOT / "scripts" / "research_output"

# Rate limit: 15 RPM for free tier
REQUEST_DELAY = 4.5  # seconds between requests (safe margin)

RESEARCH_PROMPT = """You are a gaming compatibility researcher for LinuxPlayDB, a database of Steam games focused on Linux gaming and Ray Tracing.

Research the game **{name}** (Steam App ID: {app_id}).

Search the web for information from these sources:
- ProtonDB (https://www.protondb.com/app/{app_id})
- PCGamingWiki
- Reddit r/linux_gaming, r/SteamDeck, r/amd
- GitHub issues for vkd3d-proton, DXVK, Proton, Mesa/RADV
- Steam community forums

I need the following information:

## 1. AMD GPU Ray Tracing compatibility
Classify as ONE of:
- "amd_ok" = RT and/or PT works correctly on AMD RDNA2+ GPUs
- "amd_pt" = Path tracing works on AMD but standard RT has issues
- "amd_rt_only" = Ray tracing works but path tracing does NOT on AMD
- "nvidia_only" = RT/PT only works on NVIDIA, crashes or broken on AMD
- "unknown" = Not enough information found

## 2. Linux launch options and environment variables
Find any Steam launch options or env vars needed for this game on Linux, such as:
- gamemoderun, mangohud, PROTON_*, VKD3D_*, DXVK_*, RADV_*, MESA_* variables
- Proton version recommendations (GE-Proton, Proton Experimental, etc.)

## 3. Linux status
- Does it work on Linux via Proton? Native Linux build?
- What is its ProtonDB rating? (platinum/gold/silver/bronze/borked)
- Any anti-cheat blocking Linux?

## 4. Useful links
Find 2-5 actual URLs that are helpful for running this game on Linux/AMD.

RESPOND ONLY with valid JSON in this exact format (no markdown, no explanation, ONLY the JSON object):

{{
  "app_id": {app_id},
  "name": "{name}",
  "amd_status": "amd_ok|amd_pt|amd_rt_only|nvidia_only|unknown",
  "amd_notes_en": "Brief explanation of AMD RT status",
  "amd_notes_es": "Breve explicación del estado AMD RT",
  "linux_status": "works|cmd|broken|check|unknown",
  "launch_options": "Steam launch options string or null",
  "env_vars": {{"VAR_NAME": "value"}} ,
  "proton_version": "Recommended Proton version or null",
  "protondb_tier": "platinum|gold|silver|bronze|borked|unknown",
  "native_linux": false,
  "anticheat": "none|EAC|BattlEye|other or null",
  "anticheat_linux": "supported|denied|broken|null",
  "linux_notes_en": "Brief Linux compatibility notes",
  "linux_notes_es": "Breves notas de compatibilidad Linux",
  "useful_links": [
    {{
      "url": "https://actual-url-here",
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
- Only include information you actually found. Do NOT fabricate data.
- If you can't find info about AMD RT, set amd_status to "unknown".
- If you can't find launch options, set launch_options to null and env_vars to {{}}.
- useful_links must contain REAL URLs you found during search. Do not invent URLs.
- Set confidence to "low" if information is scarce or uncertain.
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
        # Games with RT/PT that lack AMD status or Linux commands
        cur.execute("""
            SELECT g.app_id, g.name
            FROM games g
            LEFT JOIN graphics_features gf ON g.app_id = gf.app_id
            LEFT JOIN linux_compat lc ON g.app_id = lc.app_id
            WHERE g.type = 'game'
              AND (
                gf.amd_status IS NULL
                OR lc.linux_status IS NULL
                OR lc.launch_options IS NULL
              )
            ORDER BY g.name
        """)

    rows = [dict(r) for r in cur.fetchall()]
    conn.close()

    if limit and not app_id:
        rows = rows[:limit]

    return rows


def research_game(client: genai.Client, game: dict, max_retries: int = 3) -> dict | None:
    """Research a single game using Gemini with search grounding."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    prompt = RESEARCH_PROMPT.format(
        name=game["name"],
        app_id=game["app_id"],
        date=today,
    )

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    temperature=0.1,
                ),
            )

            text = response.text.strip()

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
            # Rate limit: wait and retry
            if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                # Extract retry delay from error if available
                wait = 30
                match = re.search(r"retry in ([\d.]+)s", err_str, re.IGNORECASE)
                if match:
                    wait = int(float(match.group(1))) + 2
                if attempt < max_retries:
                    print(f"  [WAIT] Rate limited. Waiting {wait}s... (attempt {attempt}/{max_retries})")
                    time.sleep(wait)
                    continue
                else:
                    print(f"  [SKIP] Rate limited after {max_retries} retries. Skipping.")
                    return None
            else:
                print(f"  [ERROR] API error for {game['name']}: {e}")
                return None

    return None


def save_results(results: list[dict]) -> None:
    """Save research results into the manual JSON files."""
    # Load existing data
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
        description="Research game compatibility using Gemini AI with web search"
    )
    parser.add_argument("--app-id", type=int, help="Research a specific game by Steam App ID")
    parser.add_argument("--limit", type=int, help="Maximum number of games to research")
    parser.add_argument("--dry-run", action="store_true", help="Show games to research without calling the API")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY, help=f"Seconds between API calls (default: {REQUEST_DELAY})")
    args = parser.parse_args()

    # Check API key
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key and not args.dry_run:
        print("[ERROR] GEMINI_API_KEY environment variable not set.")
        print("Get your free key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Check database
    if not DB_FILE.exists():
        print(f"[ERROR] Database not found: {DB_FILE}")
        print("Run 'python build_db.py' first.")
        sys.exit(1)

    # Get games to research
    games = get_games_to_research(DB_FILE, app_id=args.app_id, limit=args.limit)

    if not games:
        print("[INFO] No games need research. All games have AMD status and Linux commands.")
        return

    print(f"LinuxPlayDB — AI Research ({len(games)} games)")
    print(f"Model: gemini-2.0-flash (free tier)")
    print(f"Delay: {args.delay}s between requests")
    print(f"Estimated time: ~{len(games) * args.delay / 60:.0f} minutes\n")

    if args.dry_run:
        print("Games to research:")
        for g in games:
            print(f"  [{g['app_id']}] {g['name']}")
        print(f"\nTotal: {len(games)} games")
        return

    # Initialize Gemini client
    client = genai.Client(api_key=api_key)

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

        # Rate limiting (skip delay on last item)
        if i < len(games):
            time.sleep(args.delay)

    # Final save
    if results:
        save_results(results)
        save_full_research(results)

    print(f"\nDone! Success: {success}, Failed: {failed}, Total: {len(games)}")


if __name__ == "__main__":
    main()
