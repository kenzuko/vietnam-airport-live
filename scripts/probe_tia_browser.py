from __future__ import annotations

import asyncio
from playwright.async_api import async_playwright

URLS = [
    ("arrival", "https://tia.vietnamairport.vn/ArrDom"),
    ("departure", "https://tia.vietnamairport.vn/DepDom"),
]
TERMINALS = ("T1", "T3", "T2")


def compact(value: str, limit: int = 6000) -> str:
    return " ".join(value.split())[:limit]


async def dump_tables(page, direction: str, terminal: str) -> None:
    print(f"\n--- {direction.upper()} {terminal} ---", flush=True)
    print("BODY", compact(await page.locator("body").inner_text(), 9000), flush=True)

    tables = page.locator("table")
    count = await tables.count()
    print(f"TABLE_COUNT {count}", flush=True)
    for i in range(count):
        table = tables.nth(i)
        if not await table.is_visible():
            continue
        headers = await table.locator("thead th").all_inner_texts()
        rows = table.locator("tbody tr")
        row_count = await rows.count()
        print(f"TABLE {i} HEADERS={headers} ROWS={row_count}", flush=True)
        for j in range(min(row_count, 20)):
            cells = await rows.nth(j).locator("td").all_inner_texts()
            print(f"ROW {i}:{j} {cells}", flush=True)

    grids = page.locator(".k-grid")
    print(f"GRID_COUNT {await grids.count()}", flush=True)
    for i in range(await grids.count()):
        grid = grids.nth(i)
        if await grid.is_visible():
            print(f"GRID {i} TEXT={compact(await grid.inner_text(), 5000)}", flush=True)


async def select_terminal(page, terminal: str) -> None:
    links = page.locator("a.nav-link")
    target = links.filter(has_text=terminal).first
    if await target.count() == 0:
        raise RuntimeError(f"terminal link {terminal} not found")
    before = await target.get_attribute("class")
    print(f"CLICK {terminal} class_before={before}", flush=True)
    await target.click()
    await page.wait_for_timeout(2500)
    after = await target.get_attribute("class")
    print(f"CLICK {terminal} class_after={after}", flush=True)


async def probe(page, direction: str, url: str) -> None:
    print(f"\n=== PROBE {direction.upper()} {url} ===", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(8000)
    print("TITLE", await page.title(), flush=True)

    for terminal in TERMINALS:
        try:
            await select_terminal(page, terminal)
            await dump_tables(page, direction, terminal)
        except Exception as exc:
            print(f"TERMINAL_ERROR {direction} {terminal} {type(exc).__name__}: {exc}", flush=True)


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
