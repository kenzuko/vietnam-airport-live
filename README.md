# Vietnam Airport Live

Public airport operations dashboard for Vietnam, starting with **SGN - Tan Son Nhat International Airport**.

## Phase 1 - SGN standalone

- Official-source-first collector
- ACV flight search API as primary source
- TIA FIDS endpoints as fallback
- Static JSON cache for fast GitHub Pages delivery
- Arrivals / departures / terminal filters
- Accent-insensitive search
- Delay calculation from scheduled vs estimated time
- Data health and last-good-data protection

## Architecture

```text
ACV / TIA
   ↓
GitHub Actions collector
   ↓
data/sgn.json
   ↓
GitHub Pages
   ↓
val.openphuquoc.com
```

The frontend never calls ACV/TIA directly. This avoids browser CORS/session issues and keeps page load fast.

## Data policy

If all upstream sources fail, the collector exits without replacing the last known good dataset. The UI exposes data age so stale data is visible rather than silently presented as live.
