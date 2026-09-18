# Vietnam Airport Live

Public airport operations dashboard for Vietnam, starting with **SGN - Tân Sơn Nhất International Airport**.

## Phase 1 - SGN standalone

- Fast static delivery on GitHub Pages
- Arrivals / departures / T1 / T2 / T3
- Accent-insensitive search
- Scheduled and updated time handling
- Delay calculation
- Live-data freshness and last-known-good protection
- Rolling daily observation archive
- Optional schedule-baseline layer for broader coverage
- Statistics and history kept separate from the current live window

## Architecture

```text
Airport live data
      ↓
Collector + validation
      ↓
data-live branch
      ↓
Normalized JSON
      ↓
GitHub Pages
      ↓
val.openphuquoc.com
```

A separate optional schedule-baseline collector can enrich the live window without exposing any API key to the browser.

## Data semantics

`Current window` is the set of flights available in the latest live airport display. It is **not** the airport's full-day traffic count.

`Observed today` is the deduplicated set accumulated by the collector since the beginning of the day. It becomes a complete-day archive only after collection has covered the day from near midnight through at least 23:30.

The UI must not label either number as the airport's official total for the day unless full-day coverage has been independently verified.

## Data safety

If collection or validation fails, the system keeps the last known good dataset instead of replacing it with an empty or suspicious response. Data age is exposed to the UI so stale information can be identified.
