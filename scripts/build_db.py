#!/usr/bin/env python3
"""Build the LinuxPlayDB SQLite database.

Orchestrator script that:
1. Creates the database schema
2. Runs seed migration (HTML -> SQLite)
3. Loads manual JSON data
4. Optionally fetches from online sources (NVIDIA, Steam, ProtonDB, etc.)
5. Inserts device/handheld data
6. Reports statistics

Usage:
    python build_db.py              # Full build (seed + manual data)
    python build_db.py --fetch      # Full build + online fetch
    python build_db.py --seed-only  # Only migrate seed data
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "data"
SCRIPTS_DIR = ROOT / "scripts"
MANUAL_DIR = SCRIPTS_DIR / "manual"
DB_FILE = DATA_DIR / "linuxplaydb.db"
SITE_DB = ROOT / "site" / "data" / "linuxplaydb.db"

SCHEMA = """
-- Core games table
CREATE TABLE IF NOT EXISTS games (
    app_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'game',
    release_date TEXT,
    genres TEXT,
    steam_url TEXT,
    header_image TEXT
);
CREATE INDEX IF NOT EXISTS idx_games_name ON games(name);
CREATE INDEX IF NOT EXISTS idx_games_type ON games(type);

-- Graphics features (RT, DLSS, FSR)
CREATE TABLE IF NOT EXISTS graphics_features (
    app_id INTEGER PRIMARY KEY REFERENCES games(app_id),
    rt_type TEXT DEFAULT 'none',
    dlss_sr BOOLEAN DEFAULT 0,
    dlss_fg BOOLEAN DEFAULT 0,
    dlss_rr BOOLEAN DEFAULT 0,
    dlss_mfg BOOLEAN DEFAULT 0,
    dlaa BOOLEAN DEFAULT 0,
    fsr4 BOOLEAN DEFAULT 0,
    fsr3 BOOLEAN DEFAULT 0,
    fsr2 BOOLEAN DEFAULT 0,
    xess BOOLEAN DEFAULT 0,
    amd_status TEXT,
    notes_en TEXT,
    notes_es TEXT
);

-- Linux compatibility
CREATE TABLE IF NOT EXISTS linux_compat (
    app_id INTEGER PRIMARY KEY REFERENCES games(app_id),
    native_linux BOOLEAN DEFAULT 0,
    protondb_tier TEXT,
    proton_version TEXT,
    deck_status TEXT,
    linux_status TEXT,
    launch_options TEXT,
    env_vars TEXT,
    anticheat TEXT,
    anticheat_linux TEXT,
    notes_en TEXT,
    notes_es TEXT
);

-- Devices (handhelds, GPUs)
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    manufacturer TEXT,
    category TEXT,
    chipset TEXT,
    gpu TEXT,
    gpu_arch TEXT,
    gpu_cus INTEGER,
    ram_mb INTEGER,
    display TEXT,
    battery_wh REAL,
    tdp_range TEXT,
    os_default TEXT,
    linux_support TEXT,
    region TEXT,
    rt_capable BOOLEAN DEFAULT 0,
    release_year INTEGER,
    price_usd_base INTEGER,
    notes_en TEXT,
    notes_es TEXT
);

-- Per-game per-device compatibility
CREATE TABLE IF NOT EXISTS device_compat (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER REFERENCES games(app_id),
    device_id TEXT REFERENCES devices(device_id),
    status TEXT,
    settings TEXT,
    fps_estimate TEXT,
    tdp_watts INTEGER,
    notes_en TEXT,
    notes_es TEXT,
    UNIQUE(app_id, device_id)
);

-- Useful links per game
CREATE TABLE IF NOT EXISTS useful_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_id INTEGER REFERENCES games(app_id),
    url TEXT NOT NULL,
    title_en TEXT NOT NULL,
    title_es TEXT,
    source TEXT,
    link_type TEXT
);

-- Data source metadata
CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    last_updated TEXT,
    entries_count INTEGER,
    url TEXT,
    notes TEXT
);
"""


def create_schema(db_path: Path) -> None:
    """Create all tables and indexes."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()
    print(f"[OK] Schema created: {db_path}")


def load_manual_json(db_path: Path) -> None:
    """Load hand-curated JSON data into the database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Build name->app_id index for matching research data by name
    cur.execute("SELECT app_id, name FROM games")
    name_to_id = {}
    for row in cur.fetchall():
        name_to_id[row[1].strip().lower()] = row[0]

    def resolve_app_id(entry):
        """Resolve app_id: try direct match first, then match by name."""
        aid = entry.get("app_id")
        if aid and cur.execute("SELECT 1 FROM games WHERE app_id = ?", (aid,)).fetchone():
            return aid
        name = entry.get("name", "").strip().lower()
        return name_to_id.get(name)

    # AMD specific data
    amd_file = MANUAL_DIR / "amd_specific.json"
    if amd_file.exists():
        data = json.loads(amd_file.read_text())
        updated = 0
        for entry in data.get("games", []):
            app_id = resolve_app_id(entry)
            if not app_id:
                continue
            cur.execute(
                """UPDATE graphics_features SET amd_status = ?, notes_en = COALESCE(?, notes_en)
                   WHERE app_id = ?""",
                (entry.get("amd_status"), entry.get("notes_en"), app_id)
            )
            if cur.rowcount > 0:
                updated += 1
        print(f"[OK] AMD data: {len(data.get('games', []))} entries ({updated} updated)")

    # Linux commands
    cmd_file = MANUAL_DIR / "linux_commands.json"
    if cmd_file.exists():
        data = json.loads(cmd_file.read_text())
        updated = 0
        for entry in data.get("games", []):
            app_id = resolve_app_id(entry)
            if not app_id:
                continue
            env_json = None
            if entry.get("env_vars") and isinstance(entry["env_vars"], dict) and len(entry["env_vars"]) > 0:
                env_json = json.dumps(entry["env_vars"])

            # Update linux_status only if research found something better than "check"
            new_status = entry.get("linux_status")
            if new_status and new_status not in ("unknown", "check"):
                status_clause = "linux_status = COALESCE(CASE WHEN linux_status IN ('check', '') OR linux_status IS NULL THEN ? ELSE linux_status END, linux_status)"
            else:
                status_clause = "linux_status = linux_status"
                new_status = None

            cur.execute(
                f"""UPDATE linux_compat
                   SET launch_options = COALESCE(?, launch_options),
                       env_vars = COALESCE(?, env_vars),
                       proton_version = COALESCE(CASE WHEN proton_version LIKE '%Check%' OR proton_version IS NULL THEN ? ELSE proton_version END, proton_version),
                       protondb_tier = COALESCE(CASE WHEN ? NOT IN ('unknown', '') THEN ? ELSE protondb_tier END, protondb_tier),
                       native_linux = CASE WHEN ? = 1 THEN 1 ELSE native_linux END,
                       anticheat = COALESCE(?, anticheat),
                       anticheat_linux = COALESCE(?, anticheat_linux),
                       notes_en = COALESCE(?, notes_en),
                       notes_es = COALESCE(?, notes_es),
                       {status_clause}
                   WHERE app_id = ?""",
                (
                    entry.get("launch_options"),
                    env_json,
                    entry.get("proton_version"),
                    entry.get("protondb_tier", "unknown"),
                    entry.get("protondb_tier"),
                    1 if entry.get("native_linux") else 0,
                    entry.get("anticheat"),
                    entry.get("anticheat_linux"),
                    entry.get("notes_en"),
                    entry.get("notes_es"),
                    *([new_status] if new_status else []),
                    app_id,
                )
            )
            if cur.rowcount > 0:
                updated += 1
        print(f"[OK] Linux commands: {len(data.get('games', []))} entries ({updated} updated)")

    # Useful links
    links_file = MANUAL_DIR / "useful_links.json"
    if links_file.exists():
        data = json.loads(links_file.read_text())
        inserted = 0
        for entry in data.get("links", []):
            app_id = resolve_app_id(entry)
            if not app_id:
                continue
            cur.execute(
                """INSERT OR IGNORE INTO useful_links (app_id, url, title_en, title_es, source, link_type)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    app_id,
                    entry.get("url"),
                    entry.get("title_en"),
                    entry.get("title_es"),
                    entry.get("source"),
                    entry.get("link_type"),
                )
            )
            if cur.rowcount > 0:
                inserted += 1
        print(f"[OK] Useful links: {len(data.get('links', []))} entries ({inserted} inserted)")

    # Handheld compatibility
    handheld_file = MANUAL_DIR / "handheld_compat.json"
    if handheld_file.exists():
        data = json.loads(handheld_file.read_text())
        for entry in data.get("compat", []):
            cur.execute(
                """INSERT OR REPLACE INTO device_compat
                   (app_id, device_id, status, settings, fps_estimate, tdp_watts, notes_en, notes_es)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    entry.get("app_id"),
                    entry.get("device_id"),
                    entry.get("status"),
                    json.dumps(entry["settings"]) if entry.get("settings") else None,
                    entry.get("fps_estimate"),
                    entry.get("tdp_watts"),
                    entry.get("notes_en"),
                    entry.get("notes_es"),
                )
            )
        print(f"[OK] Handheld compat: {len(data.get('compat', []))} entries")

    conn.commit()
    conn.close()


def load_devices(db_path: Path) -> None:
    """Insert all tracked devices (handhelds + reference GPUs)."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    devices = [
        # Valve
        ("steam_deck_lcd", "Steam Deck LCD", "Valve", "handheld", "AMD Van Gogh", "RDNA 2 (Custom)", "RDNA2", 8, 16384, "1280x800 7\" 60Hz LCD", 40.0, "4-15W", "SteamOS", "native", "global", 0, 2022, 399, "Original Steam Deck. No hardware RT.", "Steam Deck original. Sin RT por hardware."),
        ("steam_deck_oled", "Steam Deck OLED", "Valve", "handheld", "AMD Sephiroth", "RDNA 2 (Custom)", "RDNA2", 8, 16384, "1280x800 7.4\" 90Hz OLED", 50.0, "4-15W", "SteamOS", "native", "global", 0, 2023, 549, "OLED version, better battery. No HW RT.", "Version OLED, mejor bateria. Sin RT por hardware."),
        # Lenovo
        ("legion_go", "Legion Go", "Lenovo", "handheld", "AMD Z1 Extreme", "Radeon 780M", "RDNA3", 12, 16384, "2560x1600 8.8\" 144Hz IPS", 49.2, "15-30W", "Windows", "bazzite", "global", 1, 2023, 699, "Detachable controllers. RDNA3 12CU.", "Controles desmontables. RDNA3 12CU."),
        ("legion_go_s_steamos", "Legion Go S (SteamOS)", "Lenovo", "handheld", "Ryzen Z2 Go", "RDNA 2", "RDNA2", 12, 16384, "1920x1200 8\" 120Hz IPS", 55.5, "15-30W", "SteamOS", "native", "global", 0, 2025, 399, "Budget SteamOS handheld. RDNA2 limited RT.", "Handheld SteamOS economico. RT limitado RDNA2."),
        ("legion_go_s_win", "Legion Go S (Windows)", "Lenovo", "handheld", "AMD Z1 Extreme", "Radeon 780M", "RDNA3", 12, 16384, "1920x1200 8\" 120Hz IPS", 55.5, "15-30W", "Windows", "bazzite", "global", 1, 2025, 499, "Windows version with Z1 Extreme.", "Version Windows con Z1 Extreme."),
        ("legion_go_2_win", "Legion Go 2 (Windows)", "Lenovo", "handheld", "Ryzen Z2 Extreme", "Radeon 890M", "RDNA3.5", 16, 16384, "2560x1600 8.8\" 144Hz IPS", 74.0, "15-35W", "Windows", "bazzite", "global", 1, 2025, 799, "Z2 Extreme flagship. RDNA 3.5 16CU RT capable.", "Flagship Z2 Extreme. RDNA 3.5 16CU con RT."),
        ("legion_go_2_steamos", "Legion Go 2 (SteamOS)", "Lenovo", "handheld", "Ryzen Z2 Extreme", "Radeon 890M", "RDNA3.5", 16, 16384, "2560x1600 8.8\" 144Hz IPS", 74.0, "15-35W", "SteamOS", "native", "global", 1, 2026, None, "SteamOS variant. RDNA 3.5 16CU.", "Variante SteamOS. RDNA 3.5 16CU."),
        # ASUS/ROG
        ("rog_ally_2023", "ROG Ally (2023)", "ASUS", "handheld", "AMD Z1 Extreme", "Radeon 780M", "RDNA3", 12, 16384, "1920x1080 7\" 120Hz IPS", 40.0, "15-30W", "Windows", "bazzite", "global", 1, 2023, 699, "First ROG handheld. RDNA3 12CU.", "Primer handheld ROG. RDNA3 12CU."),
        ("rog_ally_x", "ROG Ally X", "ASUS", "handheld", "AMD Z1 Extreme", "Radeon 780M", "RDNA3", 12, 24576, "1920x1080 7\" 120Hz IPS", 80.0, "15-30W", "Windows", "bazzite", "global", 1, 2024, 799, "More RAM and battery than original Ally.", "Mas RAM y bateria que el Ally original."),
        ("rog_xbox_ally", "ROG Xbox Ally", "ASUS", "handheld", "Ryzen Z2 A", "RDNA 2", "RDNA2", 8, 16384, "1920x1080 7\" 120Hz IPS", 40.0, "6-20W", "Windows", "bazzite", "global", 0, 2025, 399, "Budget Xbox-branded. RDNA2 8CU, no RT.", "Economico con marca Xbox. RDNA2 8CU, sin RT."),
        ("rog_xbox_ally_x", "ROG Xbox Ally X", "ASUS", "handheld", "Ryzen Z2 Extreme", "Radeon 890M", "RDNA3.5", 16, 24576, "1920x1080 7\" 120Hz IPS", 80.0, "15-35W", "Windows", "bazzite", "global", 1, 2025, 799, "Z2 Extreme Xbox edition. RDNA 3.5 RT.", "Edicion Xbox Z2 Extreme. RDNA 3.5 RT."),
        # MSI
        ("msi_claw_7_ai", "MSI Claw 7 AI+", "MSI", "handheld", "Intel Core Ultra 7 258V", "Intel Arc 140V", "Xe2", None, 16384, "1920x1080 7\" 120Hz IPS", 53.0, "17-37W", "Windows", "problematic", "global", 1, 2025, 699, "Lunar Lake. Intel Xe2, problematic Linux.", "Lunar Lake. Intel Xe2, Linux problematico."),
        ("msi_claw_8_ai", "MSI Claw 8 AI+", "MSI", "handheld", "Intel Core Ultra 7 258V", "Intel Arc 140V", "Xe2", None, 16384, "1920x1200 8\" 120Hz IPS", 80.0, "17-37W", "Windows", "problematic", "global", 1, 2025, 799, "Larger Claw variant. Same Intel issues.", "Variante Claw mas grande. Mismos problemas Intel."),
        ("msi_claw_a8", "MSI Claw A8", "MSI", "handheld", "Ryzen Z2 Extreme", "Radeon 890M", "RDNA3.5", 16, 16384, "1920x1200 8\" 120Hz IPS", 80.0, "15-35W", "Windows", "bazzite", "global", 1, 2025, 799, "AMD variant. RDNA 3.5 16CU.", "Variante AMD. RDNA 3.5 16CU."),
        # OneXPlayer
        ("onexfly_f1_pro_8840u", "OneXFly F1 Pro (8840U)", "OneXPlayer", "handheld", "Ryzen 7 8840U", "Radeon 780M", "RDNA3", 12, 16384, "1920x1080 7\" 120Hz AMOLED", 48.5, "15-28W", "Windows", "bazzite", "global", 1, 2024, 799, "AMOLED display. RDNA3 12CU limited RT.", "Pantalla AMOLED. RDNA3 12CU RT limitado."),
        ("onexfly_f1_pro_hx370", "OneXFly F1 Pro (HX370)", "OneXPlayer", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "1920x1080 7\" 120Hz AMOLED", 48.5, "15-54W", "Windows", "bazzite", "global", 1, 2025, 999, "Strix Point APU. RDNA 3.5 16CU RT.", "APU Strix Point. RDNA 3.5 16CU RT."),
        ("onexfly_apex_395", "OneXFly Apex (Max+ 395)", "OneXPlayer", "handheld", "Ryzen AI Max+ 395", "Radeon 8060S", "RDNA3.5", 40, 65536, "2560x1600 10.1\" IPS", 115.0, "45-125W", "Windows", "bazzite", "global", 1, 2025, 1999, "Strix Halo 40CU. Most powerful handheld.", "Strix Halo 40CU. Handheld mas potente."),
        ("onexfly_apex_385", "OneXFly Apex (Max 385)", "OneXPlayer", "handheld", "Ryzen AI Max 385", "Radeon 8050S", "RDNA3.5", 32, 32768, "2560x1600 10.1\" IPS", 115.0, "45-125W", "Windows", "bazzite", "global", 1, 2025, 1499, "Strix Halo 32CU variant.", "Variante Strix Halo 32CU."),
        # AYANEO
        ("ayaneo_2s", "AYANEO 2S", "AYANEO", "handheld", "AMD 7840U", "Radeon 780M", "RDNA3", 12, 16384, "1920x1200 7\" IPS", 50.3, "15-28W", "Windows", "bazzite", "global", 1, 2023, 899, "Premium build quality. RDNA3.", "Calidad de construccion premium. RDNA3."),
        ("ayaneo_kun", "AYANEO Kun", "AYANEO", "handheld", "AMD 7840U", "Radeon 780M", "RDNA3", 12, 32768, "2560x1600 8.4\" IPS", 75.0, "15-54W", "Windows", "bazzite", "global", 1, 2023, 1099, "Large screen variant. Up to 54W TDP.", "Variante pantalla grande. Hasta 54W TDP."),
        ("ayaneo_3_hx370", "AYANEO 3 (HX370)", "AYANEO", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "1920x1200 7\" IPS", 55.0, "15-54W", "Windows", "bazzite", "global", 1, 2025, 999, "RDNA 3.5 flagship compact.", "Flagship compacto RDNA 3.5."),
        ("ayaneo_3_8840u", "AYANEO 3 (8840U)", "AYANEO", "handheld", "Ryzen 7 8840U", "Radeon 780M", "RDNA3", 12, 16384, "1920x1200 7\" IPS", 55.0, "15-28W", "Windows", "bazzite", "global", 1, 2025, 699, "Budget AYANEO 3 variant.", "Variante economica AYANEO 3."),
        ("ayaneo_flip_1s_kb", "AYANEO Flip 1S KB", "AYANEO", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "1920x1200 7\" IPS", 48.0, "15-54W", "Windows", "bazzite", "global", 1, 2025, 899, "Keyboard variant. RDNA 3.5.", "Variante con teclado. RDNA 3.5."),
        ("ayaneo_flip_1s_ds", "AYANEO Flip 1S DS", "AYANEO", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "Dual 1920x1200 7\" IPS", 48.0, "15-54W", "Windows", "bazzite", "global", 1, 2025, 999, "Dual screen variant. RDNA 3.5.", "Variante doble pantalla. RDNA 3.5."),
        ("ayaneo_next_ii", "AYANEO NEXT II", "AYANEO", "handheld", "Ryzen AI Max+ 395", "Radeon 8060S", "RDNA3.5", 40, 65536, "2560x1600 8.4\" IPS", 80.0, "45-125W", "Windows", "bazzite", "global", 1, 2025, 1999, "Strix Halo 40CU desktop-class.", "Strix Halo 40CU clase desktop."),
        ("ayaneo_pocket_ds", "AYANEO Pocket DS", "AYANEO", "handheld", "Snapdragon G3x Gen 2", "Adreno", "Adreno", None, 12288, "Dual 1080p 5\"", 38.0, None, "Android", "none", "global", 0, 2025, 499, "Android handheld. No PC gaming RT.", "Handheld Android. Sin RT para PC gaming."),
        # GPD
        ("gpd_win4_2024", "GPD Win 4 (2024)", "GPD", "handheld", "AMD 7840U", "Radeon 780M", "RDNA3", 12, 32768, "1920x1080 6\" IPS", 45.6, "15-28W", "Windows", "bazzite", "global", 1, 2024, 799, "Clamshell format. RDNA3 12CU.", "Formato clamshell. RDNA3 12CU."),
        ("gpd_win4_2025_hx370", "GPD Win 4 2025 (HX370)", "GPD", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "1920x1080 6\" IPS", 45.6, "15-54W", "Windows", "bazzite", "global", 1, 2025, 999, "Strix Point upgrade. 16CU RDNA 3.5.", "Upgrade Strix Point. 16CU RDNA 3.5."),
        ("gpd_win_mini_2025", "GPD Win Mini 2025", "GPD", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "1920x1080 7\" IPS", 44.0, "15-54W", "Windows", "bazzite", "global", 1, 2025, 799, "Mini clamshell. RDNA 3.5.", "Mini clamshell. RDNA 3.5."),
        ("gpd_win5_395", "GPD Win 5 (Max+ 395)", "GPD", "handheld", "Ryzen AI Max+ 395", "Radeon 8060S", "RDNA3.5", 40, 65536, "2560x1440 8\" IPS", 100.0, "45-125W", "Windows", "bazzite", "global", 1, 2025, 1999, "Strix Halo 40CU. Desktop replacement.", "Strix Halo 40CU. Reemplazo de desktop."),
        ("gpd_win5_385", "GPD Win 5 (Max 385)", "GPD", "handheld", "Ryzen AI Max 385", "Radeon 8050S", "RDNA3.5", 32, 32768, "2560x1440 8\" IPS", 100.0, "45-125W", "Windows", "bazzite", "global", 1, 2025, 1499, "Strix Halo 32CU.", "Strix Halo 32CU."),
        # Zotac
        ("zotac_zone", "Zotac Zone", "Zotac", "handheld", "Ryzen 7 8840U", "Radeon 780M", "RDNA3", 12, 16384, "1920x1080 7\" AMOLED", 48.5, "15-28W", "Windows", "bazzite", "global", 1, 2024, 699, "AMOLED. Good Bazzite support.", "AMOLED. Buen soporte Bazzite."),
        ("zotac_zone_2", "Zotac Zone 2", "Zotac", "handheld", "Ryzen AI 9 HX 370", "Radeon 890M", "RDNA3.5", 16, 32768, "1920x1200 7\" AMOLED", 55.0, "15-54W", "Manjaro", "native", "global", 1, 2025, 799, "Ships with Manjaro Linux. Native Linux!", "Viene con Manjaro Linux. Linux nativo!"),
        # Acer
        ("nitro_blaze_7", "Nitro Blaze 7", "Acer", "handheld", "Ryzen 7 8840HS", "Radeon 780M", "RDNA3", 12, 16384, "1920x1080 7\" IPS", 50.0, "15-28W", "Windows", "bazzite", "global", 1, 2025, 599, "Budget 7\" option. RDNA3.", "Opcion economica 7\". RDNA3."),
        ("nitro_blaze_8", "Nitro Blaze 8", "Acer", "handheld", "Ryzen 7 8840HS", "Radeon 780M", "RDNA3", 12, 16384, "1920x1200 8\" IPS", 55.0, "15-28W", "Windows", "bazzite", "global", 1, 2025, 699, "8\" version. RDNA3.", "Version 8\". RDNA3."),
        ("nitro_blaze_11", "Nitro Blaze 11", "Acer", "handheld", "Ryzen 7 8840HS", "Radeon 780M", "RDNA3", 12, 16384, "2560x1600 10.95\" IPS", 74.0, "15-28W", "Windows", "bazzite", "global", 1, 2025, 899, "11\" tablet-style. Detachable controllers.", "Estilo tablet 11\". Controles desmontables."),
        # Android/ARM
        ("ayn_odin_2", "AYN Odin 2", "AYN", "handheld", "Snapdragon 8 Gen 2", "Adreno 740", "Adreno", None, 16384, "1920x1080 6\" IPS", 55.0, None, "Android", "none", "global", 1, 2023, 399, "First mobile with HW RT (Android). Not for PC games.", "Primer movil con RT HW (Android). No para juegos PC."),
        ("ayn_odin_3", "AYN Odin 3", "AYN", "handheld", "Snapdragon 8 Elite", "Adreno 830", "Adreno", None, 16384, "1920x1200 7\" AMOLED", 60.0, None, "Android", "none", "global", 1, 2025, 499, "QSR 2.0, advanced RT. 43 FPS RT benchmark, UE5.", "QSR 2.0, RT avanzado. 43 FPS RT benchmark, UE5."),
        ("ayn_thor", "AYN Thor", "AYN", "handheld", "Snapdragon 8 Gen 2", "Adreno 740", "Adreno", None, 16384, "Dual screen", 50.0, None, "Android", "none", "global", 1, 2025, 499, "Dual screen. HW RT (Android only).", "Doble pantalla. RT HW (solo Android)."),
        ("retroid_pocket_6", "Retroid Pocket 6", "Retroid", "handheld", "Snapdragon 8 Gen 2", "Adreno 740", "Adreno", None, 12288, "1920x1080 5.5\"", 38.0, None, "Android", "none", "global", 1, 2026, 299, "Budget RT Android handheld.", "Handheld Android RT economico."),
    ]

    for d in devices:
        cur.execute(
            """INSERT OR REPLACE INTO devices
               (device_id, name, manufacturer, category, chipset, gpu, gpu_arch, gpu_cus,
                ram_mb, display, battery_wh, tdp_range, os_default, linux_support, region,
                rt_capable, release_year, price_usd_base, notes_en, notes_es)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            d
        )

    conn.commit()
    conn.close()
    print(f"[OK] Devices: {len(devices)} entries")


def run_fetch_scripts(db_path: Path) -> None:
    """Run online data fetchers (NVIDIA, ProtonDB, Steam, etc.)."""
    fetchers = [
        ("fetch_nvidia", "NVIDIA RTX DB"),
        ("fetch_protondb", "ProtonDB"),
        ("fetch_steam", "Steam Store API"),
        ("fetch_deck_compat", "Steam Deck Compat"),
        ("fetch_anticheat", "AreWeAntiCheatYet"),
    ]

    for module_name, label in fetchers:
        script = SCRIPTS_DIR / f"{module_name}.py"
        if not script.exists():
            print(f"[SKIP] {label}: {script.name} not found")
            continue

        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location(module_name, script)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "fetch"):
                count = mod.fetch(db_path)
                print(f"[OK] {label}: {count} entries")
            else:
                print(f"[SKIP] {label}: no fetch() function")
        except Exception as e:
            print(f"[ERROR] {label}: {e}")


def update_data_sources(db_path: Path) -> None:
    """Record metadata about data sources."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()

    sources = [
        ("seed", now, None, None, "Migrated from all_steam_rt_games.html"),
        ("nvidia", None, None, "https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/news/nvidia-rtx-games-engines-apps/dlss-rt-games-apps-overrides.json", "NVIDIA RTX/DLSS database"),
        ("protondb", None, None, "https://www.protondb.com/api/v1/reports/summaries/", "ProtonDB tier summaries"),
        ("steam", None, None, "https://store.steampowered.com/api/appdetails", "Steam Store API"),
        ("anticheat", None, None, "https://raw.githubusercontent.com/AreWeAntiCheatYet/AreWeAntiCheatYet/HEAD/games.json", "AreWeAntiCheatYet"),
        ("manual", now, None, None, "Hand-curated AMD, Linux, handheld data"),
    ]

    for s in sources:
        cur.execute(
            """INSERT OR REPLACE INTO data_sources (source_id, last_updated, entries_count, url, notes)
               VALUES (?, COALESCE(?, (SELECT last_updated FROM data_sources WHERE source_id = ?)),
                       ?, ?, ?)""",
            (s[0], s[1], s[0], s[2], s[3], s[4])
        )

    conn.commit()
    conn.close()


def print_stats(db_path: Path) -> None:
    """Print database statistics."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    print("\n" + "=" * 50)
    print("DATABASE STATISTICS")
    print("=" * 50)

    tables = ["games", "graphics_features", "linux_compat", "devices", "device_compat", "useful_links"]
    for table in tables:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count} rows")

    cur.execute("SELECT COUNT(*) FROM graphics_features WHERE rt_type = 'pt'")
    pt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM graphics_features WHERE rt_type = 'rt'")
    rt = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM graphics_features WHERE fsr4 = 1")
    fsr4 = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM linux_compat WHERE linux_status = 'works'")
    works = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM linux_compat WHERE linux_status = 'broken'")
    broken = cur.fetchone()[0]

    print(f"\n  Path Tracing: {pt}")
    print(f"  Ray Tracing: {rt}")
    print(f"  FSR4: {fsr4}")
    print(f"  Linux works: {works}")
    print(f"  Linux broken: {broken}")

    size = db_path.stat().st_size
    print(f"\n  DB size: {size / 1024:.1f} KB")
    print("=" * 50)

    conn.close()


def copy_to_site(db_path: Path) -> None:
    """Copy the database to the site directory for serving."""
    site_data_dir = ROOT / "site" / "data"
    site_data_dir.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(db_path, SITE_DB)
    print(f"[OK] Copied to {SITE_DB}")


def generate_inline_db(db_path: Path) -> None:
    """Generate db_inline.js with the database embedded as base64.

    This allows the site to work from file:// without a server.
    """
    import base64

    db_bytes = db_path.read_bytes()
    b64 = base64.b64encode(db_bytes).decode("ascii")

    inline_js = ROOT / "site" / "js" / "db_inline.js"
    inline_js.write_text(
        f"// Auto-generated by build_db.py — DO NOT EDIT\n"
        f"// Database: {len(db_bytes)} bytes, base64: {len(b64)} chars\n"
        f'const LPDB_INLINE_DB = "{b64}";\n'
    )
    print(f"[OK] Inline DB: {inline_js} ({len(b64)} chars, {len(db_bytes) / 1024:.0f} KB)")


def main():
    parser = argparse.ArgumentParser(description="Build LinuxPlayDB database")
    parser.add_argument("--fetch", action="store_true", help="Fetch from online sources")
    parser.add_argument("--seed-only", action="store_true", help="Only migrate seed data")
    parser.add_argument("--inline-only", action="store_true", help="Only regenerate db_inline.js from existing DB")
    args = parser.parse_args()

    # Quick path: just regenerate inline JS from existing DB
    if args.inline_only:
        if not DB_FILE.exists():
            print(f"[ERROR] Database not found: {DB_FILE}")
            sys.exit(1)
        generate_inline_db(DB_FILE)
        print("[OK] Regenerated db_inline.js")
        return

    start = time.time()
    print("LinuxPlayDB — Database Builder")
    print(f"Output: {DB_FILE}\n")

    # Remove old DB if exists
    if DB_FILE.exists():
        DB_FILE.unlink()
        print("[OK] Removed old database")

    # Step 1: Create schema
    create_schema(DB_FILE)

    # Step 2: Migrate seed data
    from migrate_seed import migrate
    migrate(DB_FILE)

    if args.seed_only:
        print_stats(DB_FILE)
        copy_to_site(DB_FILE)
        print(f"\nDone in {time.time() - start:.1f}s")
        return

    # Step 3: Load devices
    load_devices(DB_FILE)

    # Step 4: Load manual JSON data
    load_manual_json(DB_FILE)

    # Step 5: Fetch online data (optional)
    if args.fetch:
        run_fetch_scripts(DB_FILE)

    # Step 6: Update data source metadata
    update_data_sources(DB_FILE)

    # Step 7: Stats
    print_stats(DB_FILE)

    # Step 8: Copy to site
    copy_to_site(DB_FILE)

    # Step 9: Generate inline JS for file:// support
    generate_inline_db(DB_FILE)

    print(f"\nDone in {time.time() - start:.1f}s")


if __name__ == "__main__":
    main()
