# Research Prompt: Linux-Specific Fixes & Workarounds

## Context

You are researching Linux-specific fixes, workarounds, and launch configurations for the game **{GAME_NAME}** (Steam App ID: **{APP_ID}**). This game is experiencing issues on Linux via Proton and you need to find solutions.

## Known Issue (if applicable)

**Reported problem:** {ISSUE_DESCRIPTION}

## Research Tasks

### 1. Launch Options

Find the optimal Steam launch options. Common patterns to investigate:

```
# Performance tools
gamemoderun %command%
mangohud %command%

# Proton overrides
PROTON_USE_WINED3D=1 %command%
PROTON_NO_ESYNC=1 %command%
PROTON_NO_FSYNC=1 %command%
PROTON_ENABLE_NVAPI=1 %command%
PROTON_HIDE_NVIDIA_GPU=0 %command%

# VKD3D-Proton settings
VKD3D_CONFIG=dxr %command%
VKD3D_CONFIG=dxr,dxr11 %command%
VKD3D_FEATURE_LEVEL=12_1 %command%

# DXVK settings
DXVK_ASYNC=1 %command%
DXVK_CONFIG_FILE=/path/to/dxvk.conf %command%

# Mesa/RADV settings (AMD)
RADV_PERFTEST=rt %command%
RADV_DEBUG=llvm %command%
mesa_glthread=true %command%
AMD_VULKAN_ICD=RADV %command%

# NVIDIA settings
__GL_SHADER_DISK_CACHE=1 %command%
__GL_SHADER_DISK_CACHE_SKIP_CLEANUP=1 %command%
__GL_THREADED_OPTIMIZATIONS=1 %command%

# Wine/Proton DLL overrides
WINEDLLOVERRIDES="xaudio2_7=n,b" %command%
WINEDLLOVERRIDES="d3d11=n;dxgi=n" %command%

# Gamescope (for compositing issues)
gamescope -w 1920 -h 1080 -r 60 -- %command%
```

### 2. Environment Variables

Identify all relevant environment variables for this game:
- **DXVK variables** for DX9/DX10/DX11 games
- **VKD3D-Proton variables** for DX12 games
- **Mesa/RADV variables** for AMD GPU users
- **Wine/Proton variables** for compatibility fixes
- **Game-specific variables** if any exist

### 3. Proton Version

Determine which Proton version works best:
- **Proton Experimental** — Valve's latest
- **Proton 9.x** — Stable branch
- **GE-Proton** — Community patches (specify version, e.g., GE-Proton9-20)
- Note if the game requires a specific version and newer/older versions break it

### 4. Configuration File Fixes

Check if manual config edits are needed:
- **Game config files** (INI, XML, JSON in the prefix)
- **DXVK config** (dxvk.conf) for game-specific overrides
- **Proton prefix tweaks** (regedit entries, DLL replacements)
- **Custom Proton prefix setup** steps

### 5. Workarounds for Common Issues

Research fixes for these common Linux/Proton problems:
- **Shader compilation stutters** — Pre-caching, async compilation
- **Audio crackling/no audio** — PulseAudio/PipeWire fixes, xaudio overrides
- **Controller not detected** — Steam Input config, SDL overrides
- **Cutscene issues** — Media Foundation workarounds, codec installation
- **Anti-cheat blocks** — EAC/BattlEye Proton compatibility status
- **Crashes on launch** — Missing dependencies, Proton version mismatch
- **Performance worse than Windows** — DXVK/VKD3D tuning, CPU governor
- **Online/multiplayer issues** — Network configuration, Proton compatibility

### 6. Dependency Requirements

Check if any system packages are needed:
- **Media codecs** (gstreamer plugins for cutscenes)
- **Font packages** (CJK fonts for Asian text)
- **Library dependencies** (lib32 packages, vulkan layers)

## Sources to Check

1. **ProtonDB** — https://www.protondb.com/app/{APP_ID} (read user reports carefully)
2. **PCGamingWiki** — Linux section of the game's article
3. **Valve Proton Issues** — https://github.com/ValveSoftware/Proton/issues (search for app ID)
4. **VKD3D-Proton Issues** — https://github.com/HansKristian-Work/vkd3d-proton/issues
5. **DXVK Issues** — https://github.com/doitsujin/dxvk/issues
6. **r/linux_gaming** — Reddit search for game name + "fix" or "workaround"
7. **Wine AppDB** — https://appdb.winehq.org/ (legacy but sometimes useful)
8. **Lutris** — https://lutris.net/games/ for install scripts with env vars
9. **Arch Wiki** — For general Proton/Wine troubleshooting

## Output Format

Return the data in the following JSON structure:

```json
{
  "app_id": {APP_ID},
  "name": "{GAME_NAME}",
  "launch_options": "gamemoderun %command%",
  "env_vars": {
    "VKD3D_CONFIG": "dxr",
    "DXVK_ASYNC": "1",
    "PROTON_NO_ESYNC": "1"
  },
  "proton_version": "GE-Proton9-20",
  "config_fixes": [
    {
      "file": "relative/path/to/config.ini",
      "description_en": "What to change and why",
      "description_es": "Que cambiar y por que",
      "changes": "FullScreen=1 -> FullScreen=0"
    }
  ],
  "workarounds": [
    {
      "issue_en": "Description of the issue",
      "issue_es": "Descripcion del problema",
      "fix_en": "Step-by-step fix in English",
      "fix_es": "Solucion paso a paso en espanol",
      "severity": "low|medium|high|critical"
    }
  ],
  "dependencies": [
    {
      "package": "gstreamer1-plugins-ugly",
      "reason_en": "Required for in-game cutscene playback",
      "reason_es": "Necesario para reproducir cinematicas"
    }
  ],
  "notes_en": "Summary of Linux fixes in English",
  "notes_es": "Summary of Linux fixes in Spanish",
  "useful_links": [
    {
      "url": "https://...",
      "title_en": "...",
      "title_es": "...",
      "source": "protondb|pcgamingwiki|reddit|github",
      "link_type": "fix|guide|discussion|wiki|video"
    }
  ],
  "confidence": "high|medium|low",
  "research_date": "YYYY-MM-DD"
}
```

## Important Notes

- **Test specificity matters.** A fix for Proton 8.x may not apply to Proton 9.x. Always note the Proton version context.
- **AMD vs NVIDIA fixes differ.** Clearly indicate if a fix is GPU-vendor-specific.
- **GE-Proton patches:** If GE-Proton is recommended, explain what patch it includes that mainline Proton lacks (e.g., media foundation, NVAPI).
- **Prefix paths:** Game config files are typically at `~/.local/share/Steam/steamapps/compatdata/{APP_ID}/pfx/drive_c/users/steamuser/...`
- **Order matters for env vars.** If multiple variables are needed, specify the complete launch command string.
- When multiple fixes exist for the same issue, list them from simplest to most invasive.
