from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sgn-baseline.json"
ENDPOINT = "https://airlabs.co/api/v9/schedules"
PAGE_SIZE = 50
MAX_PAGES_PER_DIRECTION = 4

# Keep the baseline on fields documented as available to Free keys.
FIELDS = ",".join([
    "airline_iata",
    "flight_iata",
    "flight_number",
    "dep_iata",
    "arr_iata",
    "dep_time",
    "arr_time",
])


def fetch_json(params: dict[str, Any]) -> dict[str, Any]:
    url = ENDPOINT + "?" + urlencode(params)
    req = Request(url, headers={
        "Accept": "application/json",
        "User-Agent": "VietnamAirportLive/1.0",
    })
    with urlopen(req, timeout=25) as res:
        return json.loads(res.read().decode("utf-8"))


def collect_direction(api_key: str, direction: str) -> tuple[list[dict[str, Any]], int]:
    airport_param = "arr_iata" if direction == "arrival" else "dep_iata"
    rows: list[dict[str, Any]] = []
    calls = 0
    offset = 0

    for _ in range(MAX_PAGES_PER_DIRECTION):
        payload = fetch_json({
            airport_param: "SGN",
            "_fields": FIELDS,
            "limit": PAGE_SIZE,
            "offset": offset,
            "api_key": api_key,
        })
        calls += 1

        if payload.get("error"):
            raise RuntimeError(str(payload["error"]))

        batch = payload.get("response")
        if not isinstance(batch, list):
            raise RuntimeError("AirLabs response is missing response[]")

        for item in batch:
            if not isinstance(item, dict):
                continue
            flight = {
                "direction": direction,
                "airline_iata": item.get("airline_iata"),
                "flight_number": item.get("flight_iata") or item.get("flight_number"),
                "origin": item.get("dep_iata"),
                "destination": item.get("arr_iata"),
                "scheduled_departure": item.get("dep_time"),
                "scheduled_arrival": item.get("arr_time"),
            }
            rows.append(flight)

        request_meta = payload.get("request") if isinstance(payload.get("request"), dict) else {}
        has_more = bool(payload.get("has_more") or request_meta.get("has_more"))
        if len(batch) < PAGE_SIZE and not has_more:
            break
        offset += PAGE_SIZE

    return rows, calls


def dedupe(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (
            row.get("direction"),
            row.get("flight_number"),
            row.get("origin"),
            row.get("destination"),
            row.get("scheduled_departure"),
            row.get("scheduled_arrival"),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def main() -> int:
    api_key = os.environ.get("AIRLABS_API_KEY", "").strip()
    if not api_key:
        print("AIRLABS_API_KEY not configured - baseline collection skipped.")
        return 0

    generated = datetime.now(TZ)
    all_rows: list[dict[str, Any]] = []
    calls = 0

    try:
        for direction in ("arrival", "departure"):
            rows, used = collect_direction(api_key, direction)
            all_rows.extend(rows)
            calls += used
    except Exception as exc:
        print(f"AirLabs baseline failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    rows = dedupe(all_rows)
    arrivals = sum(r["direction"] == "arrival" for r in rows)
    departures = sum(r["direction"] == "departure" for r in rows)

    payload = {
        "airport": "SGN",
        "generated_at": generated.isoformat(timespec="seconds"),
        "coverage": "AirLabs schedule window - documented up to about 10 hours ahead",
        "complete_day": False,
        "summary": {
            "total": len(rows),
            "arrivals": arrivals,
            "departures": departures,
            "api_calls": calls,
        },
        "flights": rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    print(f"AirLabs SGN baseline: {len(rows)} rows using {calls} request(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
