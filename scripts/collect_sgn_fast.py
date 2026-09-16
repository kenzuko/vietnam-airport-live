from __future__ import annotations

import asyncio
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from playwright.async_api import Page, async_playwright

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "sgn.json"
URLS = {
    "arrival": "https://tia.vietnamairport.vn/ArrDom",
    "departure": "https://tia.vietnamairport.vn/DepDom",
}
TERMINALS = (("T1", "1"), ("T3", "3"), ("T2", "2"))
AIRLINES = {
    "VN": "Vietnam Airlines", "VJ": "VietJet Air", "VU": "Vietravel Airlines",
    "QH": "Bamboo Airways", "BL": "Pacific Airlines", "SQ": "Singapore Airlines",
    "TG": "Thai Airways", "AK": "AirAsia", "FD": "Thai AirAsia", "TR": "Scoot",
    "KE": "Korean Air", "OZ": "Asiana Airlines", "CX": "Cathay Pacific",
    "BR": "EVA Air", "CI": "China Airlines", "CZ": "China Southern",
    "MU": "China Eastern", "CA": "Air China", "JL": "Japan Airlines",
    "NH": "ANA", "QR": "Qatar Airways", "EK": "Emirates", "JQ": "Jetstar",
    "5J": "Cebu Pacific", "TK": "Turkish Airlines", "QF": "Qantas",
    "PR": "Philippine Airlines", "UA": "United Airlines", "AA": "American Airlines",
    "DL": "Delta Air Lines", "SK": "SAS",
}


def now_vn() -> datetime:
    return datetime.now(TZ)


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def hhmm(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def split_numbers(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    out: list[str] = []
    for part in text.split(","):
        n = re.sub(r"\s+", "", part).upper()
        if n and n not in out:
            out.append(n)
    return out


def airline(number: str | None) -> str | None:
    if not number:
        return None
    m = re.match(r"([A-Z0-9]{2,3})", number)
    return AIRLINES.get(m.group(1)) if m else None


def delay_minutes(scheduled: str | None, estimated: str | None) -> int | None:
    if not scheduled or not estimated:
        return None
    sh, sm = map(int, scheduled.split(":"))
    eh, em = map(int, estimated.split(":"))
    diff = eh * 60 + em - sh * 60 - sm
    if diff < -720:
        diff += 1440
    elif diff > 720:
        diff -= 1440
    return diff


def service_date(scheduled: str | None, generated: datetime) -> tuple[str | None, int]:
    if not scheduled:
        return None, 0
    h, m = map(int, scheduled.split(":"))
    diff = h * 60 + m - (generated.hour * 60 + generated.minute)
    offset = 1 if diff < -720 else (-1 if diff > 720 else 0)
    return (generated.date() + timedelta(days=offset)).isoformat(), offset


async def visible_rows(page: Page) -> list[list[str]]:
    out: list[list[str]] = []
    tables = page.locator("table:visible")
    for i in range(await tables.count()):
        rows = tables.nth(i).locator("tbody tr")
        for j in range(await rows.count()):
            cells = [clean(x) or "" for x in await rows.nth(j).locator("td").all_inner_texts()]
            if cells:
                out.append(cells)
    return out


async def terminal_rows(page: Page, terminal_num: str) -> list[list[str]]:
    return [r for r in await visible_rows(page) if len(r) >= 5 and r[4] == terminal_num]


async def wait_initial_grid(page: Page, direction: str) -> None:
    for _ in range(24):
        if await visible_rows(page):
            return
        await page.wait_for_timeout(400)
    raise RuntimeError(f"{direction} grid did not load")


async def switch_terminal(page: Page, terminal: str, terminal_num: str) -> list[list[str]]:
    rows = await terminal_rows(page, terminal_num)
    if rows:
        return rows
    target = page.locator("a.nav-link").filter(has_text=terminal).first
    if await target.count() == 0:
        raise RuntimeError(f"terminal {terminal} tab not found")
    await target.click(timeout=6000)
    for _ in range(16):
        await page.wait_for_timeout(450)
        rows = await terminal_rows(page, terminal_num)
        if rows:
            return rows
    raise RuntimeError(f"terminal {terminal} did not load")


def parse_row(direction: str, terminal: str, cells: list[str]) -> dict[str, Any] | None:
    if direction == "arrival":
        if len(cells) < 7:
            return None
        scheduled, estimated, route, flight_cell, _, belt, status = cells[:7]
        gate = counter = None
    else:
        if len(cells) < 8:
            return None
        scheduled, estimated, route, flight_cell, _, counter, gate, status = cells[:8]
        belt = None

    scheduled = hhmm(scheduled)
    estimated = hhmm(estimated)
    route = clean(route)
    numbers = split_numbers(flight_cell)
    if not scheduled or not route or not numbers:
        return None

    return {
        "direction": direction,
        "terminal": terminal,
        "flight_numbers": numbers,
        "route_airport": route,
        "scheduled": scheduled,
        "estimated": estimated,
        "status": clean(status),
        "gate": clean(gate),
        "counter": clean(counter),
        "belt": clean(belt),
        "is_international": terminal == "T2",
    }


def item_key(x: dict[str, Any]) -> str:
    location = x.get("belt") or x.get("gate") or x.get("counter") or ""
    return "|".join([x.get("direction") or "", x.get("terminal") or "", x.get("scheduled") or "", x.get("route_airport") or "", str(location)])


def merge(store: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
    key = item_key(item)
    if key not in store:
        store[key] = item
        return
    old = store[key]
    nums = list(old.get("flight_numbers") or [])
    for n in item.get("flight_numbers") or []:
        if n not in nums:
            nums.append(n)
    old["flight_numbers"] = nums
    for field in ("estimated", "status", "gate", "counter", "belt"):
        if item.get(field) not in (None, ""):
            old[field] = item[field]


async def collect_direction(context, direction: str) -> tuple[dict[str, dict[str, Any]], list[str]]:
    page = await context.new_page()
    store: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    try:
        await page.goto(URLS[direction], wait_until="domcontentloaded", timeout=25000)
        await wait_initial_grid(page, direction)
        for terminal, num in TERMINALS:
            await switch_terminal(page, terminal, num)
            before = len(store)
            for sample in range(2):
                rows = await terminal_rows(page, num)
                for row in rows:
                    item = parse_row(direction, terminal, row)
                    if item:
                        merge(store, item)
                if sample == 0:
                    await page.wait_for_timeout(650)
            notes.append(f"{direction}/{terminal}={len(store)-before}")
    finally:
        await page.close()
    return store, notes


def finalize(store: dict[str, dict[str, Any]], generated: datetime) -> list[dict[str, Any]]:
    flights: list[dict[str, Any]] = []
    for item in store.values():
        numbers = item.get("flight_numbers") or []
        primary = numbers[0] if numbers else None
        date, offset = service_date(item.get("scheduled"), generated)
        direction = item["direction"]
        route = item["route_airport"]
        flights.append({
            **item,
            "flight_number": primary,
            "airline": airline(primary),
            "origin": route if direction == "arrival" else "SGN",
            "destination": "SGN" if direction == "arrival" else route,
            "scheduled_date": date,
            "day_offset": offset,
            "actual": None,
            "delay_minutes": delay_minutes(item.get("scheduled"), item.get("estimated")),
            "source": "Live airport data",
        })
    return sorted(flights, key=lambda f: (int(f.get("day_offset") or 0), f.get("scheduled") or "99:99", f.get("direction") or "", f.get("terminal") or ""))


def validate(flights: list[dict[str, Any]]) -> tuple[bool, str]:
    if len(flights) < 45:
        return False, f"too few flights: {len(flights)}"
    coverage = {(d, t): sum(1 for f in flights if f.get("direction") == d and f.get("terminal") == t) for d in ("arrival", "departure") for t, _ in TERMINALS}
    weak = [f"{d}/{t}={n}" for (d, t), n in coverage.items() if n < 5]
    if weak:
        return False, "weak coverage: " + ", ".join(weak)
    return True, " ".join(f"{d}/{t}={n}" for (d, t), n in coverage.items())


def write_dataset(flights: list[dict[str, Any]], generated: datetime) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    arrivals = sum(f["direction"] == "arrival" for f in flights)
    departures = sum(f["direction"] == "departure" for f in flights)
    delayed = sum((f.get("delay_minutes") or 0) >= 15 or "trễ" in (f.get("status") or "").lower() for f in flights)
    payload = {
        "airport": {"iata": "SGN", "icao": "VVTS", "name": "Tan Son Nhat International Airport", "city": "Ho Chi Minh City"},
        "date": generated.date().isoformat(),
        "generated_at": generated.isoformat(timespec="seconds"),
        "source": "Live airport data",
        "coverage": "T1, T2, T3 - current live window",
        "summary": {"total": len(flights), "arrivals": arrivals, "departures": departures, "delayed": delayed, "terminals": ["T1", "T2", "T3"]},
        "flights": flights,
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {len(flights)} SGN flights", flush=True)


async def run() -> int:
    generated = now_vn()
    print(f"Collecting SGN at {generated.isoformat()}", flush=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True, args=["--disable-dev-shm-usage", "--no-sandbox"])
        context = await browser.new_context(locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh", viewport={"width": 1440, "height": 1000})
        try:
            arrival_result, departure_result = await asyncio.gather(
                collect_direction(context, "arrival"),
                collect_direction(context, "departure"),
            )
        finally:
            await context.close()
            await browser.close()

    store: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    for part_store, part_notes in (arrival_result, departure_result):
        for item in part_store.values():
            merge(store, item)
        notes.extend(part_notes)

    flights = finalize(store, generated)
    ok, reason = validate(flights)
    print(f"validation={reason}", flush=True)
    print(" ".join(notes), flush=True)
    if not ok:
        print("Dataset rejected; preserving previous cache.", file=sys.stderr, flush=True)
        return 2
    write_dataset(flights, generated)
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except Exception as exc:
        print(f"collector fatal: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
