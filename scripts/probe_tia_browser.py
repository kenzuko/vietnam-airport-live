from __future__ import annotations

import asyncio
from playwright.async_api import async_playwright

URLS = [
    ("arrival", "https://tia.vietnamairport.vn/ArrDom"),
    ("departure", "https://tia.vietnamairport.vn/DepDom"),
]
TERMINALS = (("T1", "1"), ("T3", "3"), ("T2", "2"))


def compact(value: str, limit: int = 5000) -> str:
    return " ".join(value.split())[:limit]


async def visible_rows(page):
    tables = page.locator("table:visible")
    found = []
    for i in range(await tables.count()):
        rows = tables.nth(i).locator("tbody tr")
        if await rows.count() == 0:
            continue
        for j in range(await rows.count()):
            cells = [x.strip() for x in await rows.nth(j).locator("td").all_inner_texts()]
            if cells:
                found.append(cells)
    return found


async def active_tabs(page):
    links = page.locator("a.nav-link")
    out = []
    for i in range(await links.count()):
        a = links.nth(i)
        out.append({
            "i": i,
            "text": compact(await a.inner_text(), 80),
            "class": await a.get_attribute("class"),
            "outer": compact(await a.evaluate("el => el.outerHTML"), 900),
        })
    return out


async def wait_for_terminal_state(page, terminal_num: str, timeout_s: int = 14):
    history = []
    for second in range(timeout_s):
        await page.wait_for_timeout(1000)
        rows = await visible_rows(page)
        body = compact(await page.locator("body").inner_text(), 500)
        matching = [r for r in rows if len(r) >= 5 and r[4].strip() == terminal_num]
        history.append((second + 1, len(rows), len(matching), body[:180]))
        if matching:
            return matching, history
    return [], history


async def probe(page, direction: str, url: str) -> None:
    print(f"\n=== PROBE {direction.upper()} {url} ===", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(10000)

    print("TITLE", await page.title(), flush=True)
    print("NAV_INITIAL", await active_tabs(page), flush=True)
    initial_rows = await visible_rows(page)
    print("INITIAL_ROWS", len(initial_rows), initial_rows[:3], flush=True)
    print("INITIAL_BODY", compact(await page.locator("body").inner_text(), 1400), flush=True)

    for terminal, terminal_num in TERMINALS:
        print(f"\n--- SWITCH {direction.upper()} {terminal} ---", flush=True)
        links = page.locator("a.nav-link")
        target = links.filter(has_text=terminal).first
        if await target.count() == 0:
            print("TARGET_NOT_FOUND", terminal, flush=True)
            continue

        print("TARGET_BEFORE", compact(await target.evaluate("el => el.outerHTML"), 1200), flush=True)
        try:
            await target.click(timeout=5000)
        except Exception as exc:
            print("CLICK_ERROR", type(exc).__name__, str(exc)[:300], flush=True)
            await target.evaluate("el => el.click()")

        matching, history = await wait_for_terminal_state(page, terminal_num)
        print("SWITCH_HISTORY", history, flush=True)
        print("NAV_AFTER", await active_tabs(page), flush=True)
        rows = await visible_rows(page)
        print("ROWS_AFTER", len(rows), rows[:20], flush=True)
        print("MATCHING_TERMINAL", terminal, len(matching), matching[:10], flush=True)
        print("BODY_AFTER", compact(await page.locator("body").inner_text(), 2200), flush=True)


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            viewport={"width": 1440, "height": 1000},
        )
        for direction, url in URLS:
            page = await context.new_page()
            try:
                await probe(page, direction, url)
            except Exception as exc:
                print(f"PROBE_ERROR {url} {type(exc).__name__}: {exc}", flush=True)
            finally:
                await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
