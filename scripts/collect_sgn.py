from __future__ import annotations

import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sgn.json"
AIRPORT = "SGN"
TERMINALS = ("T1", "T2", "T3")
DIRECTIONS = ("arrival", "departure")
PAGE_SIZE = 50
MAX_PAGES = 20
TIMEOUT = (15, 35)

AIRLINES = {
    "VN": "Vietnam Airlines",
    "VJ": "VietJet Air",
    "VU": "Vietravel Airlines",
    "QH": "Bamboo Airways",
    "BL": "Pacific Airlines",
    "SQ": "Singapore Airlines",
    "TG": "Thai Airways",
    "AK": "AirAsia",
    "FD": "Thai AirAsia",
    "TR": "Scoot",
    "KE": "Korean Air",
    "OZ": "Asiana Airlines",
    "CX": "Cathay Pacific",
    "BR": "EVA Air",
    "CI": "China Airlines",
    "CZ": "China Southern",
    "MU": "China Eastern",
    "CA": "Air China",
    "JL": "Japan Airlines",
    "NH": "ANA",
    "QR": "Qatar Airways",
    "EK": "Emirates",
}


def now_vn() -> datetime:
    return datetime.now(TZ)


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def first(obj: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in obj and obj[key] not in (None, ""):
            return obj[key]
    return None


def flight_no(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    return re.sub(r"\s+", "", text).upper()


def airline_name(number: str | None, raw: dict[str, Any]) -> str | None:
    explicit = clean(first(raw, "airline", "airlineName", "hangHangKhong", "tenHangHangKhong"))
    if explicit:
        return explicit
    if not number:
        return None
    m = re.match(r"([A-Z0-9]{2,3})", number)
    return AIRLINES.get(m.group(1)) if m else None


def normalize_hhmm(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    # Prefer the last explicit HH:MM in case the source includes a date.
    matches = re.findall(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", text)
    if matches:
        h, m = matches[-1]
        return f"{int(h):02d}:{m}"
    return text


def delay_minutes(scheduled: str | None, estimated: str | None) -> int | None:
    if not scheduled or not estimated:
        return None
    if not re.fullmatch(r"\d{2}:\d{2}", scheduled) or not re.fullmatch(r"\d{2}:\d{2}", estimated):
        return None
    sh, sm = map(int, scheduled.split(":"))
    eh, em = map(int, estimated.split(":"))
    diff = (eh * 60 + em) - (sh * 60 + sm)
    if diff < -720:
        diff += 1440
    elif diff > 720:
        diff -= 1440
    return diff


def parse_route(raw_route: Any, direction: str) -> tuple[str | None, str | None, str | None]:
    route = clean(raw_route)
    if not route:
        return None, None, None
    parts = [p.strip() for p in re.split(r"\s*(?:-|–|—|→|>)\s*", route, maxsplit=1) if p.strip()]
    if len(parts) == 2:
        origin, destination = parts
    else:
        origin = None if direction == "departure" else parts[0]
        destination = parts[0] if direction == "departure" else None
    other = destination if direction == "departure" else origin
    return origin, destination, other


def normalize_acv(raw: dict[str, Any], direction: str, terminal: str) -> dict[str, Any] | None:
    number = flight_no(first(raw, "soHieuChuyenBay", "flightNo", "flightNumber", "FlightNo"))
    if not number:
        return None

    route = first(raw, "route", "tuyenBay", "routeName", "Route")
    origin, destination, other = parse_route(route, direction)

    if direction == "departure":
        scheduled = normalize_hhmm(first(raw, "gioKhoiHanh", "scheduledDeparture", "scheduledTime", "Scheduled"))
        estimated = normalize_hhmm(first(raw, "gioKhoiHanhDuKien", "estimatedDeparture", "estimatedTime", "Estimated"))
        actual = normalize_hhmm(first(raw, "gioKhoiHanhThucTe", "actualDeparture", "actualTime", "Actual"))
    else:
        scheduled = normalize_hhmm(first(raw, "gioHaCanh", "scheduledArrival", "scheduledTime", "Scheduled"))
        estimated = normalize_hhmm(first(raw, "gioHaCanhDuKien", "estimatedArrival", "estimatedTime", "Estimated"))
        actual = normalize_hhmm(first(raw, "gioHaCanhThucTe", "actualArrival", "actualTime", "Actual"))

    status = clean(first(raw, "trangThai", "status", "RemarkVn", "remark"))
    terminal_value = clean(first(raw, "terminal", "nhaGa", "Terminal")) or terminal
    gate = clean(first(raw, "gate", "cuaRaMayBay", "Gate"))
    counter = clean(first(raw, "checkInCounter", "quayThuTuc", "counter", "Counter"))
    belt = clean(first(raw, "baggageBelt", "bangChuyen", "belt", "Belt"))

    return {
        "direction": direction,
        "terminal": terminal_value,
        "flight_number": number,
        "airline": airline_name(number, raw),
        "origin": origin,
        "destination": destination,
        "route_airport": other,
        "scheduled": scheduled,
        "estimated": estimated,
        "actual": actual,
        "delay_minutes": delay_minutes(scheduled, estimated or actual),
        "status": status,
        "gate": gate,
        "counter": counter,
        "belt": belt,
        "is_international": terminal_value.upper() == "T2",
    }


def acv_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "Accept": "*/*",
            "Content-Type": "application/json",
            "Accept-Language": "vi;q=0.9,en;q=0.7",
            "Origin": "https://acv.vn",
            "Referer": "https://acv.vn/vi/chuyen-bay",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36",
        }
    )
    return s


def extract_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in ("items", "rows", "results", "data"):
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
    for key in ("items", "rows", "results", "flights", "Flights"):
        if isinstance(payload.get(key), list):
            return [x for x in payload[key] if isinstance(x, dict)]
    return []


def fetch_acv() -> tuple[list[dict[str, Any]], list[str]]:
    session = acv_session()
    date = now_vn().strftime("%Y-%m-%d")
    flights: list[dict[str, Any]] = []
    notes: list[str] = []

    for direction in DIRECTIONS:
        for terminal in TERMINALS:
            warm_params = {
                "type": direction,
                "flightDate": date,
                "terminal": terminal,
                "arrivalStation" if direction == "arrival" else "departureStation": AIRPORT,
            }
            try:
                r = session.get("https://acv.vn/vi/chuyen-bay", params=warm_params, timeout=TIMEOUT)
                notes.append(f"warmup {direction}/{terminal}={r.status_code}")
            except requests.RequestException as exc:
                notes.append(f"warmup {direction}/{terminal} error={type(exc).__name__}")

            for page in range(1, MAX_PAGES + 1):
                payload = {
                    "flightDate": date,
                    "pageIndex": page,
                    "pageSize": PAGE_SIZE,
                    "langCode": "vi",
                    "terminal": terminal,
                    "flightNo": "",
                    "departureStation": AIRPORT if direction == "departure" else "",
                    "arrivalStation": AIRPORT if direction == "arrival" else "",
                    "type": direction,
                }
                proxy_body = {"url": "/api/flights/search", "method": "POST", "body": payload}
                try:
                    response = session.post("https://acv.vn/api/proxy", json=proxy_body, timeout=TIMEOUT)
                    response.raise_for_status()
                    rows = extract_list(response.json())
                except (requests.RequestException, ValueError) as exc:
                    notes.append(f"ACV {direction}/{terminal}/p{page} error={type(exc).__name__}")
                    break

                if not rows:
                    break
                for row in rows:
                    item = normalize_acv(row, direction, terminal)
                    if item:
                        flights.append(item)
                if len(rows) < PAGE_SIZE:
                    break
                time.sleep(0.15)

    return flights, notes


def dedupe(flights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for f in flights:
        key = "|".join(
            [
                f.get("direction") or "",
                f.get("terminal") or "",
                f.get("flight_number") or "",
                f.get("scheduled") or "",
                f.get("route_airport") or "",
            ]
        )
        if key not in merged:
            merged[key] = f
        else:
            # Keep non-empty values from the newest copy.
            merged[key] = {k: (f.get(k) if f.get(k) not in (None, "") else merged[key].get(k)) for k in set(merged[key]) | set(f)}
    return sorted(merged.values(), key=lambda x: (x.get("scheduled") or "99:99", x.get("flight_number") or ""))


def validate(flights: list[dict[str, Any]]) -> tuple[bool, str]:
    if len(flights) < 20:
        return False, f"too few normalized flights: {len(flights)}"
    dirs = {f.get("direction") for f in flights}
    if not {"arrival", "departure"}.issubset(dirs):
        return False, f"missing direction coverage: {sorted(dirs)}"
    terminals = {str(f.get("terminal") or "").upper() for f in flights}
    if not terminals.intersection({"T1", "T2", "T3"}):
        return False, "terminal coverage missing"
    return True, "ok"


def write_dataset(flights: list[dict[str, Any]], notes: list[str], source: str) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    generated = now_vn()
    arrivals = sum(1 for f in flights if f["direction"] == "arrival")
    departures = sum(1 for f in flights if f["direction"] == "departure")
    delayed = sum(1 for f in flights if (f.get("delay_minutes") or 0) >= 15 or "trễ" in (f.get("status") or "").lower() or "delay" in (f.get("status") or "").lower())
    terminals = sorted({str(f.get("terminal") or "").upper() for f in flights if f.get("terminal")})

    payload = {
        "airport": {
            "iata": "SGN",
            "icao": "VVTS",
            "name": "Tan Son Nhat International Airport",
            "city": "Ho Chi Minh City",
        },
        "date": generated.strftime("%Y-%m-%d"),
        "generated_at": generated.isoformat(timespec="seconds"),
        "source": source,
        "coverage": "full",
        "summary": {
            "total": len(flights),
            "arrivals": arrivals,
            "departures": departures,
            "delayed": delayed,
            "terminals": terminals,
        },
        "flights": flights,
        "collector_notes": notes[-30:],
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {len(flights)} flights to {OUT}")


def main() -> int:
    print(f"Collecting SGN for {now_vn().isoformat()}")
    flights, notes = fetch_acv()
    flights = dedupe(flights)
    ok, reason = validate(flights)
    print(f"ACV normalized={len(flights)} validation={reason}")
    for line in notes[-12:]:
        print(line)

    if not ok:
        print("Upstream dataset rejected. Last known good data will be preserved.", file=sys.stderr)
        return 2

    write_dataset(flights, notes, "ACV official flight search API")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
