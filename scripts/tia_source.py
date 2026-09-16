from __future__ import annotations

import re
import time
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests

TIMEOUT = (5, 10)
MAX_PAGES = 8
BASE = "https://tia.vietnamairport.vn"

SOURCE_CONFIG = {
    "arrival": {
        "referers": [
            f"{BASE}/ArrDom",
            f"{BASE}/arrivals-vn",
        ],
        "computer": "T2AOSA01A",
    },
    "departure": {
        "referers": [
            f"{BASE}/DepDom",
            f"{BASE}/departures-vn",
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
        "Origin": BASE,
        "Referer": referer,
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        "X-Requested-With": "XMLHttpRequest",
    })
    return s


def _candidate_strings(text: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    patterns = [
        r'''["']([^"']{1,220}(?:api|flight|schedule|arr|dep|dom|int|ajax|getdata|search)[^"']{0,220})["']''',
        r'''(?:url|action)\s*[:=]\s*["']([^"']+)["']''',
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.I):
            value = re.sub(r"\s+", " ", match).strip()
            if not value or len(value) > 300:
                continue
            low = value.lower()
            if any(noise in low for noise in ("bootstrap", "fontawesome", "google", "facebook", "stylesheet")):
                continue
            if value not in seen:
                seen.add(value)
                candidates.append(value)
            if len(candidates) >= 25:
                return candidates
    return candidates


def _discover_assets(session: requests.Session, landing_url: str, html: str, notes: list[str]) -> None:
    notes.append(f"DISCOVERY html_len={len(html)} path={urlparse(landing_url).path}")

    inline_candidates = _candidate_strings(html)
    if inline_candidates:
        notes.append("DISCOVERY html_candidates=" + " || ".join(inline_candidates[:12]))

    script_srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, flags=re.I)
    notes.append("DISCOVERY scripts=" + " || ".join(script_srcs[-12:]))

    checked = 0
    for src in script_srcs:
        script_url = urljoin(landing_url, src)
        if urlparse(script_url).netloc != urlparse(BASE).netloc:
            continue
        if checked >= 10:
            break
        checked += 1
        try:
            r = session.get(script_url, timeout=TIMEOUT)
            notes.append(f"DISCOVERY js={urlparse(script_url).path} status={r.status_code} len={len(r.text)}")
            if r.status_code != 200:
                continue
            candidates = _candidate_strings(r.text)
            if candidates:
                notes.append(
                    f"DISCOVERY js_candidates={urlparse(script_url).path}: "
                    + " || ".join(candidates[:15])
                )
        except requests.RequestException as exc:
            notes.append(f"DISCOVERY js={urlparse(script_url).path} error={type(exc).__name__}")


def _bootstrap(direction: str, notes: list[str]) -> tuple[requests.Session, dict[str, str]] | None:
    cfg = SOURCE_CONFIG[direction]
    computer = cfg["computer"]
    view_url = f"{BASE}/FlightSchedule/getFlightView"

    for referer in cfg["referers"]:
        s = _session(referer)
        try:
            t0 = time.monotonic()
            landing = s.get(referer, timeout=TIMEOUT)
            notes.append(
                f"TIA {direction} landing={landing.status_code} "
                f"{time.monotonic()-t0:.1f}s {referer.rsplit('/',1)[-1]}"
            )

            if landing.status_code == 200:
                _discover_assets(s, referer, landing.text, notes)

            t0 = time.monotonic()
            view = s.post(view_url, data={"computerName": computer}, timeout=TIMEOUT)
            notes.append(f"TIA {direction} legacy_view={view.status_code} {time.monotonic()-t0:.1f}s")
            view.raise_for_status()
            dates = _extract_dates(view.text)
            if len(dates) == 3:
                return s, dates
            notes.append(f"TIA {direction} view_dates={','.join(sorted(dates)) or 'none'}")
        except requests.RequestException as exc:
            notes.append(f"TIA {direction} bootstrap={type(exc).__name__}")
    return None


def fetch_tia(
    normalize: Callable[[dict[str, Any], str], dict[str, Any] | None]
) -> tuple[list[dict[str, Any]], list[str]]:
    notes: list[str] = []
    all_flights: list[dict[str, Any]] = []
    get_time = f"{BASE}/FlightSchedule/getTime"
    get_data = f"{BASE}/FlightSchedule/getData"

    for direction in ("arrival", "departure"):
        boot = _bootstrap(direction, notes)
        if not boot:
            continue
        session, dates = boot
        computer = SOURCE_CONFIG[direction]["computer"]

        try:
            r = session.post(get_time, timeout=TIMEOUT)
            notes.append(f"TIA {direction} legacy_time={r.status_code}")
        except requests.RequestException as exc:
            notes.append(f"TIA {direction} legacy_time={type(exc).__name__}")

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

            if len(rows) < 10:
                break
            time.sleep(0.1)

    return all_flights, notes
