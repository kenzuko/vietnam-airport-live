from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from tia_source import fetch_tia

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sgn.json"

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
    return re.sub(r"\s+", "", text).upper() if text else None


def airline_name(number: str | None, raw: dict[str, Any]) -> str | None:
    explicit = clean(first(raw, "Airline", "AirlineName", "airline", "airlineName"))
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
    matches = re.findall(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", text)
    if matches:
        h, m = matches[-1]
        return f"{int(h):02d}:{m}"
    return None


def delay_minutes(scheduled: str | None, effective: str | None) -> int | None:
    if not scheduled or not effective:
        return None
    if not re.fullmatch(r"\d{2}:\d{2}", scheduled) or not re.fullmatch(r"\d{2}:\d{2}", effective):
        return None
    sh, sm = map(int, scheduled.split(":"))
    eh, em = map(int, effective.split(":"))
    diff = (eh * 60 + em) - (sh * 60 + sm)
    if diff < -720:
        diff += 1440
    elif diff > 720:
        diff -= 1440
    return diff


def terminal_from_raw(raw: dict[str, Any]) -> str | None:
    value = clean(first(raw, "Terminal", "terminal", "TerminalNo", "TerminalName"))
    if not value:
        return None
    m = re.search(r"\bT?([123])\b", value, flags=re.I)
    return f"T{m.group(1)}" if m else value.upper()


def normalize_tia(raw: dict[str, Any], direction: str) -> dict[str, Any] | None:
    number = flight_no(first(raw, "FlightNo", "FlightNumber", "flightNo", "flightNumber"))
    airport = clean(first(raw, "Airport", "airport", "City", "city"))
    scheduled = normalize_hhmm(first(raw, "Scheduled", "scheduled"))
    estimated = normalize_hhmm(first(raw, "Estimated", "estimated"))
    actual = normalize_hhmm(first(raw, "Actual", "ActualTime", "actual", "actualTime"))

    if not number or not airport or not scheduled:
        return None

    status = clean(first(raw, "RemarkVn", "RemarkVN", "Remark", "Status", "status"))
    terminal = terminal_from_raw(raw)
    gate = clean(first(raw, "Gate", "gate", "GateNo", "BoardingGate"))
    counter = clean(first(raw, "Counter", "counter", "CheckInCounter", "CheckinCounter"))
    belt = clean(first(raw, "Belt", "belt", "BaggageBelt", "Carousel"))

    if direction == "arrival":
        origin = airport
        destination = "SGN"
    else:
        origin = "SGN"
        destination = airport

    return {
        "direction": direction,
        "terminal": terminal,
        "flight_number": number,
        "airline": airline_name(number, raw),
        "origin": origin,
        "destination": destination,
        "route_airport": airport,
        "scheduled": scheduled,
        "estimated": estimated,
        "actual": actual,
        "delay_minutes": delay_minutes(scheduled, estimated or actual),
        "status": status,
        "gate": gate,
        "counter": counter,
        "belt": belt,
        "is_international": True if terminal == "T2" else (False if terminal in {"T1", "T3"} else None),
        "source": "TIA FIDS",
    }


def dedupe(flights: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for f in flights:
        key = "|".join(
            [
                f.get("direction") or "",
                f.get("flight_number") or "",
                f.get("scheduled") or "",
                f.get("route_airport") or "",
            ]
        )
        if key not in merged:
            merged[key] = f
            continue
        old = merged[key]
        merged[key] = {
            k: (f.get(k) if f.get(k) not in (None, "") else old.get(k))
            for k in set(old) | set(f)
        }
    return sorted(
        merged.values(),
        key=lambda x: (x.get("scheduled") or "99:99", x.get("flight_number") or ""),
    )


def direction_overlap(flights: list[dict[str, Any]]) -> float:
    arrivals = {
        (f.get("flight_number"), f.get("scheduled"), f.get("route_airport"))
        for f in flights
        if f.get("direction") == "arrival"
    }
    departures = {
        (f.get("flight_number"), f.get("scheduled"), f.get("route_airport"))
        for f in flights
        if f.get("direction") == "departure"
    }
    if len(arrivals) < 5 or len(departures) < 5:
        return 0.0
    return len(arrivals & departures) / min(len(arrivals), len(departures))


def validate(flights: list[dict[str, Any]]) -> tuple[bool, str]:
    if len(flights) < 20:
        return False, f"too few normalized flights: {len(flights)}"

    arrivals = [f for f in flights if f.get("direction") == "arrival"]
    departures = [f for f in flights if f.get("direction") == "departure"]
    if len(arrivals) < 8 or len(departures) < 8:
        return False, f"direction coverage weak: arrivals={len(arrivals)} departures={len(departures)}"

    overlap = direction_overlap(flights)
    if overlap > 0.75:
        return False, f"arrival/departure overlap suspicious: {overlap:.0%}"

    valid_time = sum(1 for f in flights if f.get("scheduled")) / len(flights)
    valid_route = sum(1 for f in flights if f.get("route_airport")) / len(flights)
    if valid_time < 0.9 or valid_route < 0.9:
        return False, f"field completeness weak: time={valid_time:.0%} route={valid_route:.0%}"

    return True, f"ok arrivals={len(arrivals)} departures={len(departures)} overlap={overlap:.0%}"


def write_dataset(
    flights: list[dict[str, Any]],
    notes: list[str],
    source: str,
    coverage: str,
) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    generated = now_vn()
    arrivals = sum(1 for f in flights if f["direction"] == "arrival")
    departures = sum(1 for f in flights if f["direction"] == "departure")
    delayed = sum(
        1
        for f in flights
        if (f.get("delay_minutes") or 0) >= 15
        or "trễ" in (f.get("status") or "").lower()
        or "delay" in (f.get("status") or "").lower()
    )
    terminals = sorted(
        {str(f.get("terminal") or "").upper() for f in flights if f.get("terminal")}
    )

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
        "coverage": coverage,
        "summary": {
            "total": len(flights),
            "arrivals": arrivals,
            "departures": departures,
            "delayed": delayed,
            "terminals": terminals,
        },
        "flights": flights,
        "collector_notes": notes[-50:],
    }

    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tmp.replace(OUT)
    print(f"Wrote {len(flights)} flights to {OUT}", flush=True)


def main() -> int:
    print(f"Collecting SGN via TIA FIDS at {now_vn().isoformat()}", flush=True)
    flights, notes = fetch_tia(normalize_tia)
    flights = dedupe(flights)
    ok, reason = validate(flights)

    print(f"TIA normalized={len(flights)} validation={reason}", flush=True)
    for line in notes:
        print(line, flush=True)

    if not ok:
        print(
            "TIA dataset rejected. Last known good data will be preserved.",
            file=sys.stderr,
            flush=True,
        )
        return 2

    write_dataset(
        flights,
        notes,
        source="TIA official FIDS",
        coverage="current FIDS board",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
