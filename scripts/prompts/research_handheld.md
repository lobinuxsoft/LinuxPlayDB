# Research Prompt: Handheld Device Compatibility

## Context

You are researching the game **{GAME_NAME}** (Steam App ID: **{APP_ID}**) on the handheld device **{DEVICE_NAME}** (Device ID: **{DEVICE_ID}**) for the LinuxPlayDB database. Your goal is to find optimal settings, expected performance, and any device-specific issues.

## Device Specifications Reference

Use the appropriate specs for the target device:

| Device | APU/GPU | VRAM | Display | TDP Range |
|--------|---------|------|---------|-----------|
| Steam Deck LCD | Zen2 / RDNA2 (8 CU) | 16GB shared | 1280x800 | 4-15W |
| Steam Deck OLED | Zen2 / RDNA2 (8 CU) | 16GB shared | 1280x800 | 4-15W |
| ROG Ally | Z1 Extreme / RDNA3 (12 CU) | 16GB shared | 1920x1080 | 9-30W |
| ROG Ally X | Z1 Extreme / RDNA3 (12 CU) | 24GB shared | 1920x1080 | 9-30W |
| Legion Go | Z1 Extreme / RDNA3 (12 CU) | 16GB shared | 2560x1600 | 8-30W |
| MSI Claw | Core Ultra / Arc (8 Xe) | 16GB shared | 1920x1080 | 10-35W |

## Research Tasks

### 1. Baseline Performance

Determine expected FPS at the device's native resolution with default/medium settings:
- Average FPS in typical gameplay
- 1% low FPS (frame time spikes)
- Areas with notable FPS drops (specific levels, effects, etc.)

### 2. Optimal Settings

Find the best balance of visual quality and performance for the target device:
- **Resolution:** Native, or lower with FSR/upscaling?
- **Quality preset:** Low/Medium/High?
- **FSR/RSR/upscaling:** Enabled? Which mode? (Quality, Balanced, Performance, Ultra Performance)
- **Individual settings to lower:** Shadows, reflections, draw distance, etc.
- **Frame rate target:** 30fps lock? 40fps lock? Unlocked?
- **VSync / Frame limiter:** Recommendations
- **RT on handhelds:** Is it feasible at reduced settings? Usually not, but note if possible.

### 3. TDP and Battery

- **Recommended TDP (watts):** What TDP provides the best efficiency?
- **Battery life estimate:** Hours of gameplay at recommended settings
- **TDP sweet spot:** Where does increasing TDP stop providing meaningful FPS gains?

### 4. Device-Specific Issues

Check for problems specific to this device:
- **Controller mapping:** Do built-in controls work correctly? Gyro support?
- **Display issues:** Scaling problems at non-native resolution? HDR behavior?
- **Sleep/resume:** Does the game handle sleep/resume properly?
- **Audio:** Any audio crackling or latency issues?
- **Storage:** Game size, loading times on internal SSD vs microSD

### 5. Linux-Specific (for SteamOS/Linux handhelds)

If the device runs SteamOS or Linux:
- **Proton compatibility on this device specifically**
- **Gamescope issues:** Any problems with the compositor?
- **Mangohud readings:** Reference performance data if available
- **Steam Input:** Controller profile recommendations

## Sources to Check

1. **Steam Deck Verified** — Valve's official compatibility status
2. **ProtonDB** — Filter reports by "Steam Deck" or device
3. **r/SteamDeck** — Reddit search for game + settings
4. **r/ROGAlly** — Reddit search (if ROG Ally target)
5. **r/LegionGo** — Reddit search (if Legion Go target)
6. **YouTube** — Search "{GAME_NAME} {DEVICE_NAME} settings" for benchmark videos
7. **ShareDeck** — https://sharedeck.games/ for community settings
8. **Steam Community Guides** — Look for handheld optimization guides

## Output Format

Return the data in the following JSON structure:

```json
{
  "app_id": {APP_ID},
  "device_id": "{DEVICE_ID}",
  "status": "verified|playable|issues|broken",
  "settings": {
    "resolution": "1280x800",
    "quality": "medium",
    "fsr": true,
    "fsr_mode": "quality",
    "fps_limit": 40,
    "half_rate_shading": false,
    "rt_enabled": false,
    "custom_settings": {
      "shadows": "low",
      "textures": "medium",
      "draw_distance": "medium"
    }
  },
  "fps_estimate": 40,
  "fps_1_percent_low": 32,
  "tdp_watts": 12,
  "battery_hours": 2.5,
  "device_issues": [
    {
      "issue_en": "...",
      "issue_es": "...",
      "workaround_en": "...",
      "workaround_es": "..."
    }
  ],
  "notes_en": "Summary of handheld experience in English",
  "notes_es": "Summary of handheld experience in Spanish",
  "confidence": "high|medium|low",
  "research_date": "YYYY-MM-DD"
}
```

## Important Notes

- FPS estimates should reflect **real gameplay**, not menu screens or benchmarks.
- TDP recommendations should prioritize **battery efficiency**, not max performance.
- For Steam Deck, 40fps/40Hz mode is often the sweet spot. Prefer 40fps targets over 60fps when it saves significant battery.
- FSR on handheld screens often looks acceptable even in Performance mode due to small screen size.
- If the game is under 15GB, note it as microSD-friendly.
- Always check if the game has a built-in frame limiter vs relying on Gamescope/RTSS.
