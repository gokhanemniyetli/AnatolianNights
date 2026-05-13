"""
Suno network diagnostic:
- suno.com/create sayfasını real Chrome ile aç
- Tüm generate/API isteklerini yakala ve ekrana yaz
- 45 saniye bekle (formla etkileşime gerek yok, sadece sayfa yüklensin)
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

SESSION_FILE = Path("config/suno_session.json")
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
]


async def main() -> None:
    real_chrome = next((p for p in CHROME_PATHS if Path(p).exists()), None)
    storage = json.loads(SESSION_FILE.read_text())

    launch_kwargs: dict = {
        "headless": False,
        "args": [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ],
    }
    if real_chrome:
        launch_kwargs["executable_path"] = real_chrome
        print(f"Launching: {real_chrome}")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(**launch_kwargs)
        context = await browser.new_context(
            storage_state=storage,
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        seen_urls: set[str] = set()

        async def on_request(req):
            url = req.url
            if any(k in url for k in ["suno", "clerk", "generate", "feed", "api"]):
                if url not in seen_urls:
                    seen_urls.add(url)
                    print(f"[REQ] {req.method:6s} {url[:120]}")

        async def on_response(resp):
            url = resp.url
            if any(k in url for k in ["generate", "feed", "api/create", "api/song"]):
                status = resp.status
                print(f"[RESP] {status} {url[:120]}")
                if status == 200:
                    try:
                        data = await resp.json()
                        print(f"  DATA keys: {list(data.keys()) if isinstance(data, dict) else type(data).__name__}")
                        print(f"  DATA preview: {json.dumps(data)[:300]}")
                    except Exception as e:
                        print(f"  (non-JSON: {e})")

        page.on("request", on_request)
        page.on("response", on_response)

        print("Navigating to suno.com/create ...")
        await page.goto("https://suno.com/create", wait_until="domcontentloaded")
        print("Page loaded. Waiting 45s — observe network traffic ...")
        print("(Pencere açıksa isterseniz 'Create' butonuna basabilirsiniz.)")

        await page.wait_for_timeout(45_000)

        # Also dump all network requests seen
        print("\n=== ALL SUNO-RELATED URLs SEEN ===")
        for url in sorted(seen_urls):
            print(" ", url[:140])

        await browser.close()
        print("Done.")


asyncio.run(main())
