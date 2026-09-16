from __future__ import annotations

import re
import time
from typing import Any, Callable

import requests

TIMEOUT = (5, 10)
MAX_PAGES = 8

SOURCE_CONFIG = {
    "arrival": {
        "referers": [
            "https://tia.vietnamairport.vn/ArrDom",
            "https://tia.vietnamairport.vn/arrivals-vn",
        ],
        "computer": "T2AOSA01A",
    },
    "departure": {
        "referers": [
            "https://tia.vietnamairport.vn/DepDom",
            "https://tia.vietnamairport.vn/departures-vn",
        ],
        "computer": "T2AOSD01A",
    },
}


def _extract_dates(html: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for key in ("LastModifiedDate", "FlightViewLastModifiedDate", "FlightViewTemplateLastModifiedDate"):
        patterns = [
            rf'class=["\']{re.escape(key)}["\'][^>]*>([^<]+)<',
            rf'id=["\']{re.escape(key)}["\'][^>]*>([^<]+)<',
            rf'name=["\']{re.escape(key)}["\'][^>]*value=["\']([^"\']+)',
        ]
        for pattern in patterns:
            m = re.search(pattern, html, flags=re.I)
            if m:
                out[key] = m.group(1).strip()
                break
    return out


def _session(referer: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "vi;q=0.9,en;q=0.7",
        "Origin": "https://tia.vietnamairport.vn",
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def _bootstrap(direction: str, notes: list[str]) -> tuple[requests.Session, dict[str, str]] | None:
    cfg = SOURCE_CONFIG[direction]
    computer = cfg["computer"]
    view_url = "https://tia.vietnamairport.vn/FlightSchedule/getFlightView"

    for referer in cfg["referers"]:
        s = _session(referer)
        try:
            t0 = time.monotonic()
            landing = s.get(referer, timeout=TIMEOUT)
            notes.append(f"TIA {direction} landing={landing.status_code} {time.monotonic()-t0:.1f}s {referer.rsplit('/',1)[-1]}")

            t0 = time.monotonic()
            view = s.post(view_url, data={"computerName": computer}, timeout=TIMEOUT)
            notes.append(f"TIA {direction} view={view.status_code} {time.monotonic()-t0:.1f}s")
            view.raise_for_status()
            dates = _extract_dates(view.text)
            if len(dates) == 3:
                return s, dates
            notes.append(f"TIA {direction} view_dates={','.join(sorted(dates)) or 'none'}")
        except requests.RequestException as exc:
            notes.append(f"TIA {direction} bootstrap={type(exc).__name__}")
    return None


def fetch_tia(normalize: Callable[[dict[str, Any], str], dict[str, Any] | None]) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    all_flights: list[dict[str, Any]] = []
    get_time = "https://tia.vietnamairport.vn/FlightSchedule/getTime"
    get_data = "https://tia.vietnamairport.vn/FlightSchedule/getData"

    for direction in ("arrival", "departure"):
        boot = _bootstrap(direction, notes)
        if not boot:
            continue
        session, dates = boot
        computer = SOURCE_CONFIG[direction]["computer"]

        try:
            r = session.post(get_time, timeout=TIMEOUT)
            notes.append(f"TIA {direction} time={r.status_code}")
        except requests.RequestException as exc:
            notes.append(f"TIA {direction} time={type(exc).__name__}")

        for page in range(1, MAX_PAGES + 1):
            payload = {"computerName": computer, "page": page, **dates}
            try:
                t0 = time.monotonic()
                r = session.post(get_data, data=payload, timeout=TIMEOUT)
                elapsed = time.monotonic() - t0
                notes.append(f"TIA {direction}/p{page} status={r.status_code} {elapsed:.1f}s")
                r.raise_for_status()
                body = r.json()
            except (requests.RequestException, ValueError) as exc:
                notes.append(f"TIA {direction}/p{page} error={type(exc).__name__}")
                break

            rows = body.get("Flights", []) if isinstance(body, dict) else []
            if not isinstance(rows, list) or not rows:
                notes.append(f"TIA {direction}/p{page} rows=0")
                break

            normalized = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item = normalize(row, direction)
                if item:
                    all_flights.append(item)
                    normalized += 1
            notes.append(f"TIA {direction}/p{page} rows={len(rows)} normalized={normalized}")

            # FIDS pages are small; a short page is the end of the current board.
            if len(rows) < 10:
                break
            time.sleep(0.1)

    return all_flights, notes
