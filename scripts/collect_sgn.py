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
    "JQ": "Jetstar",
    "5J": "Cebu Pacific",
    "TK": "Turkish Airlines",
    "QF": "Qantas",
    "PR": "Philippine Airlines",
    "UA": "United Airlines",
    "AA": "American Airlines",
    "DL": "Delta Air Lines",
    "SK": "SAS",
}


def now_vn() -> datetime:
    return datetime.now(TZ)


def clean(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def normalize_hhmm(value: Any) -> str | None:
    text = clean(value)
    if not text:
        return None
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", text)
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def split_flight_numbers(value: Any) -> list[str]:
    text = clean(value)
    if not text:
        return []
    numbers: list[str] = []
    for part in text.split(","):
        number = re.sub(r"\s+", "", part).upper()
        if number and number not in numbers:
            numbers.append(number)
    return numbers


def airline_name(number: str | None) -> str | None:
    if not number:
        return None
    m = re.match(r"([A-Z0-9]{2,3})", number)
    return AIRLINES.get(m.group(1)) if m else None


def delay_minutes(scheduled: str | None, estimated: str | None) -> int | None:
    if not scheduled or not estimated:
        return None
    sh, sm = map(int, scheduled.split(":"))
    eh, em = map(int, estimated.split(":"))
    diff = eh * 60 + em - (sh * 60 + sm)
    if diff < -720:
        diff += 1440
    elif diff > 720:
        diff -= 1440
    return diff


def service_date(scheduled: str | None, generated: datetime) -> tuple[str | None, int]:
    if not scheduled:
        return None, 0
    h, m = map(int, scheduled.split(":"))
    sched_min = h * 60 + m
    now_min = generated.hour * 60 + generated.minute
    diff = sched_min - now_min
    offset = 1 if diff < -720 else (-1 if diff > 720 else 0)
    date = (generated.date() + timedelta(days=offset)).isoformat()
    return date, offset


async def visible_rows(page: Page) -> list[list[str]]:
    rows_out: list[list[str]] = []
    tables = page.locator("table:visible")
    for i in range(await tables.count()):
        rows = tables.nth(i).locator("tbody tr")
        for j in range(await rows.count()):
            cells = [clean(x) or "" for x in await rows.nth(j).locator("td").all_inner_texts()]
            if cells:
                rows_out.append(cells)
    return rows_out


async def rows_for_terminal(page: Page, terminal_num: str) -> list[list[str]]:
    return [r for r in await visible_rows(page) if len(r) >= 5 and r[4] == terminal_num]


async def switch_terminal(page: Page, terminal: str, terminal_num: str) -> list[list[str]]:
    current = await rows_for_terminal(page, terminal_num)
    if current:
        return current

    target = page.locator("a.nav-link").filter(has_text=terminal).first
    if await target.count() == 0:
        raise RuntimeError(f"terminal tab {terminal} not found")

    await target.click(timeout=6000)
    for _ in range(18):
        await page.wait_for_timeout(750)
        current = await rows_for_terminal(page, terminal_num)
        if current:
            return current
    raise RuntimeError(f"terminal {terminal} did not load matching FIDS rows")


def pager_button_is_page_two(meta: dict[str, Any]) -> bool:
    text = (meta.get("text") or "").strip().lower()
    title = (meta.get("title") or "").strip().lower()
    aria = (meta.get("aria") or "").strip().lower()
    combined = f"{text} {title} {aria}"
    return text == "2" or "page 2" in combined or "trang 2" in combined


async def go_page_two(page: Page, terminal_num: str, first_signature: tuple[str, ...]) -> bool:
    pager = page.locator(".k-pager:visible").first
    if await pager.count() == 0:
        return False

    buttons = pager.locator("button")
    for i in range(await buttons.count()):
        button = buttons.nth(i)
        meta = {
            "text": await button.inner_text(),
            "title": await button.get_attribute("title"),
            "aria": await button.get_attribute("aria-label"),
            "disabled": await button.get_attribute("aria-disabled"),
        }
        if pager_button_is_page_two(meta) and meta["disabled"] != "true":
            await button.click()
            break
    else:
        inputs = pager.locator("input")
        if await inputs.count():
            inp = inputs.first
            try:
                await inp.fill("2")
                await inp.press("Enter")
            except Exception:
                return False
        else:
            return False

    for _ in range(14):
        await page.wait_for_timeout(600)
        rows = await rows_for_terminal(page, terminal_num)
        if rows:
            sig = tuple(rows[0][:5])
            if sig != first_signature:
                return True
    return False


def row_to_snapshot(direction: str, terminal: str, cells: list[str]) -> dict[str, Any] | None:
    if direction == "arrival":
        if len(cells) < 7:
            return None
        scheduled, estimated, airport, flight_cell, terminal_num, belt, status = cells[:7]
        counter = gate = None
    else:
        if len(cells) < 8:
            return None
        scheduled, estimated, airport, flight_cell, terminal_num, counter, gate, status = cells[:8]
        belt = None

    scheduled = normalize_hhmm(scheduled)
    estimated = normalize_hhmm(estimated)
    airport = clean(airport)
    numbers = split_flight_numbers(flight_cell)
    if not scheduled or not airport or not numbers:
        return None

    return {
        "direction": direction,
        "terminal": terminal,
        "flight_numbers": numbers,
        "route_airport": airport,
        "scheduled": scheduled,
        "estimated": estimated,
        "status": clean(status),
        "gate": clean(gate),
        "counter": clean(counter),
        "belt": clean(belt),
        "is_international": terminal == "T2",
    }


def slot_key(item: dict[str, Any]) -> str:
    location = item.get("belt") or item.get("gate") or item.get("counter") or ""
    return "|".join(
        [
            item.get("direction") or "",
            item.get("terminal") or "",
            item.get("scheduled") or "",
            item.get("route_airport") or "",
            str(location),
        ]
    )


def merge_snapshot(store: dict[str, dict[str, Any]], item: dict[str, Any]) -> None:
    key = slot_key(item)
    if key not in store:
        store[key] = item
        return

    old = store[key]
    numbers = list(old.get("flight_numbers") or [])
    for number in item.get("flight_numbers") or []:
        if number not in numbers:
            numbers.append(number)
    old["flight_numbers"] = numbers

    for field in ("estimated", "status", "gate", "counter", "belt"):
        if item.get(field) not in (None, ""):
            old[field] = item[field]


async def sample_page(
    page: Page,
    direction: str,
    terminal: str,
    terminal_num: str,
    store: dict[str, dict[str, Any]],
    samples: int = 3,
) -> int:
    seen = 0
    for sample_idx in range(samples):
        rows = await rows_for_terminal(page, terminal_num)
        for row in rows:
            item = row_to_snapshot(direction, terminal, row)
            if item:
                merge_snapshot(store, item)
                seen += 1
        if sample_idx < samples - 1:
            await page.wait_for_timeout(1800)
    return seen


async def collect_terminal(
    page: Page,
    direction: str,
    terminal: str,
    terminal_num: str,
    store: dict[str, dict[str, Any]],
    notes: list[str],
) -> None:
    first_rows = await switch_terminal(page, terminal, terminal_num)
    first_sig = tuple(first_rows[0][:5])
    count_before = len(store)
    sampled = await sample_page(page, direction, terminal, terminal_num, store)
    pages = 1

    try:
        if await go_page_two(page, terminal_num, first_sig):
            sampled += await sample_page(page, direction, terminal, terminal_num, store, samples=2)
            pages = 2
    except Exception as exc:
        notes.append(f"{direction}/{terminal} pager={type(exc).__name__}")

    notes.append(
        f"{direction}/{terminal} pages={pages} sampled_rows={sampled} unique_added={len(store)-count_before}"
    )


async def collect_direction(
    context,
    direction: str,
    store: dict[str, dict[str, Any]],
    notes: list[str],
) -> None:
    page = await context.new_page()
    try:
        await page.goto(URLS[direction], wait_until="domcontentloaded", timeout=30000)
        # TIA Blazor renders a placeholder first, then hydrates the Telerik grid.
        for _ in range(22):
            await page.wait_for_timeout(500)
            rows = await visible_rows(page)
            if rows:
                break
        else:
            raise RuntimeError(f"{direction} FIDS grid did not hydrate")

        for terminal, terminal_num in TERMINALS:
            await collect_terminal(page, direction, terminal, terminal_num, store, notes)
    finally:
        await page.close()


def finalize(store: dict[str, dict[str, Any]], generated: datetime) -> list[dict[str, Any]]:
    flights: list[dict[str, Any]] = []
    for item in store.values():
        numbers = item.get("flight_numbers") or []
        primary = numbers[0] if numbers else None
        scheduled_date, offset = service_date(item.get("scheduled"), generated)
        direction = item["direction"]
        airport = item["route_airport"]

        flight = {
            **item,
            "flight_number": primary,
            "flight_numbers": numbers,
            "airline": airline_name(primary),
            "origin": airport if direction == "arrival" else "SGN",
            "destination": "SGN" if direction == "arrival" else airport,
            "scheduled_date": scheduled_date,
            "day_offset": offset,
            "actual": None,
            "delay_minutes": delay_minutes(item.get("scheduled"), item.get("estimated")),
            "source": "TIA official FIDS",
        }
        flights.append(flight)

    def sort_key(f: dict[str, Any]):
        offset = int(f.get("day_offset") or 0)
        hh, mm = map(int, (f.get("scheduled") or "23:59").split(":"))
        return (offset, hh * 60 + mm, f.get("direction") or "", f.get("terminal") or "")

    return sorted(flights, key=sort_key)


def validate(flights: list[dict[str, Any]]) -> tuple[bool, str]:
    if len(flights) < 45:
        return False, f"too few flights: {len(flights)}"

    coverage: dict[tuple[str, str], int] = {}
    for direction in ("arrival", "departure"):
        for terminal, _ in TERMINALS:
            coverage[(direction, terminal)] = sum(
                1 for f in flights if f.get("direction") == direction and f.get("terminal") == terminal
            )

    weak = [f"{d}/{t}={n}" for (d, t), n in coverage.items() if n < 5]
    if weak:
        return False, "weak terminal coverage: " + ", ".join(weak)

    complete = sum(
        1
        for f in flights
        if f.get("flight_number") and f.get("scheduled") and f.get("route_airport") and f.get("terminal")
    ) / len(flights)
    if complete < 0.95:
        return False, f"field completeness={complete:.0%}"

    return True, "ok " + " ".join(f"{d}/{t}={n}" for (d, t), n in coverage.items())


def write_dataset(flights: list[dict[str, Any]], notes: list[str], generated: datetime) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    arrivals = sum(1 for f in flights if f["direction"] == "arrival")
    departures = sum(1 for f in flights if f["direction"] == "departure")
    delayed = sum(
        1
        for f in flights
        if (f.get("delay_minutes") or 0) >= 15
        or "trễ" in (f.get("status") or "").lower()
        or "delay" in (f.get("status") or "").lower()
    )
    payload = {
        "airport": {
            "iata": "SGN",
            "icao": "VVTS",
            "name": "Tan Son Nhat International Airport",
            "city": "Ho Chi Minh City",
        },
        "date": generated.date().isoformat(),
        "generated_at": generated.isoformat(timespec="seconds"),
        "source": "TIA official FIDS via Blazor Server",
        "coverage": "T1 + T3 domestic, T2 international, current FIDS window",
        "summary": {
            "total": len(flights),
            "arrivals": arrivals,
            "departures": departures,
            "delayed": delayed,
            "terminals": ["T1", "T2", "T3"],
        },
        "flights": flights,
        "collector_notes": notes[-30:],
    }
    tmp = OUT.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    tmp.replace(OUT)
    print(f"Wrote {len(flights)} SGN flights to {OUT}", flush=True)


async def run() -> int:
    generated = now_vn()
    store: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    print(f"Collecting SGN official FIDS at {generated.isoformat()}", flush=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chrome",
            headless=True,
            args=["--disable-dev-shm-usage", "--no-sandbox"],
        )
        context = await browser.new_context(
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            viewport={"width": 1440, "height": 1000},
        )
        try:
            await collect_direction(context, "arrival", store, notes)
            await collect_direction(context, "departure", store, notes)
        finally:
            await context.close()
            await browser.close()

    flights = finalize(store, generated)
    ok, reason = validate(flights)
    print(f"validation={reason}", flush=True)
    for note in notes:
        print(note, flush=True)

    if not ok:
        print("Dataset rejected. Last known good SGN cache is preserved.", file=sys.stderr, flush=True)
        return 2

    write_dataset(flights, notes, generated)
    return 0


def main() -> int:
    try:
        return asyncio.run(run())
    except Exception as exc:
        print(f"collector fatal: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
