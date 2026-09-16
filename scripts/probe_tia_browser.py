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
    out = []
    tables = page.locator("table:visible")
    for i in range(await tables.count()):
        rows = tables.nth(i).locator("tbody tr")
        for j in range(await rows.count()):
            cells = [x.strip() for x in await rows.nth(j).locator("td").all_inner_texts()]
            if cells:
                out.append(cells)
    return out


async def wait_terminal(page, terminal_num: str):
    for _ in range(20):
        rows = [r for r in await visible_rows(page) if len(r) >= 5 and r[4] == terminal_num]
        if rows:
            return rows
        await page.wait_for_timeout(700)
    return []


async def pager_dump(page):
    pagers = page.locator(".k-pager:visible")
    data = []
    for i in range(await pagers.count()):
        p = pagers.nth(i)
        data.append({
            "text": compact(await p.inner_text(), 1000),
            "html": compact(await p.evaluate("el => el.outerHTML"), 4000),
        })
    return data


async def try_next(page, terminal_num: str, first_sig: tuple[str, ...]):
    selectors = [
        '.k-pager-nav.k-pager-next:visible',
        'button[title*="next" i]:visible',
        'button[aria-label*="next" i]:visible',
        'button[title*="tiếp" i]:visible',
        'button[aria-label*="tiếp" i]:visible',
    ]
    for sel in selectors:
        loc = page.locator(sel).first
        if await loc.count() == 0:
            continue
        print("NEXT_CANDIDATE", sel, compact(await loc.evaluate("el => el.outerHTML"), 1200), flush=True)
        try:
            await loc.click(timeout=5000)
        except Exception as exc:
            print("NEXT_CLICK_ERROR", sel, type(exc).__name__, str(exc)[:200], flush=True)
            continue
        for _ in range(15):
            await page.wait_for_timeout(700)
            rows = [r for r in await visible_rows(page) if len(r) >= 5 and r[4] == terminal_num]
            if rows and tuple(rows[0][:5]) != first_sig:
                return rows
        return []
    return []


async def probe(page, direction: str, url: str):
    print(f"\n=== {direction.upper()} ===", flush=True)
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(9000)

    for terminal, terminal_num in TERMINALS:
        target = page.locator("a.nav-link").filter(has_text=terminal).first
        if await target.count() == 0:
            print("NO_TERMINAL", terminal, flush=True)
            continue
        try:
            await target.click(timeout=5000)
        except Exception:
            await target.evaluate("el => el.click()")
        rows = await wait_terminal(page, terminal_num)
        print("TERMINAL", terminal, "ROWS", len(rows), "FIRST", rows[:2], flush=True)
        print("PAGER", await pager_dump(page), flush=True)
        if rows:
            second = await try_next(page, terminal_num, tuple(rows[0][:5]))
            print("PAGE2_ROWS", terminal, len(second), "FIRST", second[:2], flush=True)


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(locale="vi-VN", timezone_id="Asia/Ho_Chi_Minh", viewport={"width": 1440, "height": 1000})
        for direction, url in URLS:
            page = await context.new_page()
            try:
                await probe(page, direction, url)
            finally:
                await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
