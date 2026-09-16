from __future__ import annotations

import asyncio
from playwright.async_api import async_playwright

URLS = [
    "https://tia.vietnamairport.vn/ArrDom",
    "https://tia.vietnamairport.vn/DepDom",
]

STATIC_SUFFIXES = (".css", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".woff", ".woff2", ".ico")


def interesting(url: str) -> bool:
    low = url.lower().split("?", 1)[0]
    if low.endswith(STATIC_SUFFIXES):
        return False
    return "tia.vietnamairport.vn" in low


async def probe(page, url: str) -> None:
    print(f"\n=== PROBE {url} ===", flush=True)

    async def on_request(req):
        if interesting(req.url):
            print(f"REQ {req.method} {req.resource_type} {req.url}", flush=True)
            if req.method not in {"GET", "HEAD"}:
                try:
                    body = req.post_data
                    if body:
                        print(f"REQ_BODY {_compact(body, 1200)}", flush=True)
                except Exception:
                    pass

    async def on_response(res):
        if interesting(res.url):
            ct = res.headers.get("content-type", "")
            print(f"RES {res.status} {ct[:80]} {res.url}", flush=True)

    def on_websocket(ws):
        print(f"WS OPEN {ws.url}", flush=True)
        ws.on("framesent", lambda payload: print(f"WS SENT {_compact(str(payload), 500)}", flush=True))
        ws.on("framereceived", lambda payload: print(f"WS RECV {_compact(str(payload), 500)}", flush=True))
        ws.on("close", lambda: print(f"WS CLOSE {ws.url}", flush=True))

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("websocket", on_websocket)

    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await page.wait_for_timeout(10000)

    print("TITLE", await page.title(), flush=True)
    print("FINAL_URL", page.url, flush=True)
    body_text = await page.locator("body").inner_text()
    print("BODY_TEXT", _compact(body_text, 8000), flush=True)

    links = await page.locator("a").evaluate_all(
        "els => els.map(a => ({text:(a.innerText||'').trim(), href:a.getAttribute('href'), cls:a.className}))"
    )
    print("LINKS", _compact(str(links), 5000), flush=True)

    buttons = await page.locator("button").evaluate_all(
        "els => els.map(b => ({text:(b.innerText||'').trim(), type:b.type, cls:b.className}))"
    )
    print("BUTTONS", _compact(str(buttons), 5000), flush=True)


def _compact(value: str, limit: int) -> str:
    return " ".join(value.split())[:limit]


async def main() -> None:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="vi-VN",
            timezone_id="Asia/Ho_Chi_Minh",
            viewport={"width": 1440, "height": 1000},
        )
        for url in URLS:
            page = await context.new_page()
            try:
                await probe(page, url)
            except Exception as exc:
                print(f"PROBE_ERROR {url} {type(exc).__name__}: {exc}", flush=True)
            finally:
                await page.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
