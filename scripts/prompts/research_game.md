# Research Prompt: Game RT/PT Compatibility & Linux Status

## Context

You are researching the game **{GAME_NAME}** (Steam App ID: **{APP_ID}**) for the LinuxPlayDB database. Your goal is to determine its ray tracing / path tracing compatibility across GPU vendors and its current status on Linux via Proton.

## Research Tasks

### 1. Ray Tracing / Path Tracing Support

Determine whether this game supports:
- **Ray Tracing (RT):** Which RT features? (reflections, shadows, global illumination, etc.)
- **Path Tracing (PT):** Full path tracing mode available?
- **RT API:** Does it use DXR 1.0, DXR 1.1, Vulkan RT, or a custom implementation?
- **RT quality levels:** What RT presets are available? (Low, Medium, High, Ultra, Psycho, etc.)

### 2. AMD GPU Compatibility

Determine the AMD status. Classify as one of:
- `amd_ok` — RT and PT work correctly on AMD RDNA2+ GPUs on Linux
- `amd_pt` — Path tracing works on AMD but standard RT has issues
- `amd_rt_only` — Ray tracing works but path tracing does not on AMD
- `nvidia_only` — RT/PT features crash, produce artifacts, or are unavailable on AMD

Check for:
- RADV driver compatibility (Mesa Vulkan driver for AMD)
- Known issues with AMD GPUs in ProtonDB reports
- Whether the game requires NVIDIA-specific extensions (e.g., NV_ray_tracing)

### 3. Linux / Proton Status

- **Proton compatibility:** Does it run on Linux via Proton? Which version works best?
- **Native Linux build:** Is there a native Linux version?
- **Anti-cheat:** Does it use EAC, BattlEye, or other anti-cheat? Is it Proton-compatible?
- **Known Linux issues:** Crashes, graphical glitches, performance problems specific to Linux

### 4. Known Issues

List any confirmed issues with:
- Shader compilation stutters on first run
- DXVK/VKD3D-Proton specific problems
- HDR support status on Linux
- FSR/DLSS availability and behavior on Linux
- Controller/input issues

## Sources to Check

1. **ProtonDB** — https://www.protondb.com/app/{APP_ID}
2. **PCGamingWiki** — https://www.pcgamingwiki.com/wiki/{GAME_NAME_URL_ENCODED}
3. **SteamDB** — https://www.steamdb.info/app/{APP_ID}/
4. **VKD3D-Proton issues** — https://github.com/HansKristian-Work/vkd3d-proton/issues
5. **DXVK issues** — https://github.com/doitsujin/dxvk/issues
6. **r/linux_gaming** — Reddit search for the game name
7. **Valve GitHub (Proton)** — https://github.com/ValveSoftware/Proton/issues

## Output Format

Return the data in the following JSON structure:

```json
{
  "app_id": {APP_ID},
  "name": "{GAME_NAME}",
  "amd_status": "amd_ok|amd_pt|amd_rt_only|nvidia_only",
  "rt_support": {
    "has_rt": true,
    "has_pt": false,
    "rt_api": "DXR 1.1",
    "rt_features": ["reflections", "shadows", "gi"],
    "rt_presets": ["Low", "Medium", "High", "Ultra"]
  },
  "linux_status": {
    "runs_on_proton": true,
    "native_linux": false,
    "recommended_proton": "Proton Experimental",
    "anti_cheat": "none",
    "anti_cheat_proton_support": null
  },
  "known_issues": [
    {
      "description_en": "...",
      "description_es": "...",
      "severity": "low|medium|high|critical",
      "workaround_en": "...",
      "workaround_es": "..."
    }
  ],
  "notes_en": "Summary of RT/AMD/Linux status in English",
  "notes_es": "Summary of RT/AMD/Linux status in Spanish",
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

- If information is uncertain, set `"confidence": "low"` and explain in notes.
- Always distinguish between RDNA2 (RX 6000) and RDNA3 (RX 7000) behavior when different.
- VKD3D-Proton is the translation layer for DX12 RT on Linux — check its compatibility.
- RADV is the open-source Mesa Vulkan driver for AMD. AMDVLK is the alternative.
- Prefer RADV-based reports as it is the most common AMD driver on Linux.
