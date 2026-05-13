"""
BrowserSunoClient — Playwright-based automation for suno.com.

First run: opens a headed browser window for the user to log in once.
            Saves cookies to config/suno_session.json.
Subsequent: headless, uses saved cookies to get a fresh JWT,
            then calls Suno's internal studio API directly.

Audio download strategy:
  1. Try WAV from Suno CDN  (<clip_id>.wav)
  2. If unavailable, download MP3 and convert to 24-bit / 48 kHz WAV with ffmpeg.
  Both paths produce a .wav file ready for DistroKid.
"""

import asyncio
import json
import logging
import subprocess
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_SESSION_FILE = Path("config/suno_session.json")
_SUNO_HOME = "https://suno.com"
_API_BASE = "https://studio-api-prod.suno.com"   # current prod domain
_CDN_BASE = "https://cdn1.suno.ai"

# Generation poll settings
_POLL_INTERVAL_S = 15       # seconds between status checks
_POLL_TIMEOUT_S = 600       # 10 minutes max wait

# Real Chrome paths (macOS)
_CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]

def _find_real_browser() -> str | None:
    for p in _CHROME_PATHS:
        if Path(p).exists():
            return p
    return None


class BrowserSunoClient:
    """
    Implements ISunoClient via Playwright + Suno internal API.

    Workflow:
      generate()       → submits generation, returns suno clip_id
      get_status()     → polls API, returns {"status": ..., "audio_url": ...}
      download_audio() → downloads WAV (or MP3→WAV fallback), returns Path
    """

    def __init__(self):
        self._jwt: str | None = None

    # ── Public sync interface (wraps async) ───────────────────────────

    def generate(self, style_prompt: str, suno_lyrics: str, song_id: str) -> str:
        """Submit to Suno. Returns clip_id (use as task_id)."""
        return asyncio.run(self._async_generate(style_prompt, suno_lyrics))

    def get_status(self, task_id: str) -> dict:
        """Poll Suno API. Returns {"status": "pending"|"complete"|"failed", "audio_url": str|None}."""
        return asyncio.run(self._async_get_status(task_id))

    def download_audio(self, task_id: str, destination: Path) -> Path:
        """
        Wait for completion, then download WAV.
        Blocks with polling until done or timeout.
        Returns the saved file path (.wav).
        """
        return asyncio.run(self._async_wait_and_download(task_id, destination))

    # ── Internal async helpers ────────────────────────────────────────

    async def _ensure_jwt(self) -> str:
        """
        Get a fresh JWT token.
        - If a saved session exists: load it into a headless browser and extract the JWT.
        - Otherwise: open a headed browser (real Chrome if available), wait for the user
          to log in, then save session.
        Returns the JWT string.
        """
        from playwright.async_api import async_playwright

        have_session = _SESSION_FILE.exists()
        real_chrome = _find_real_browser()

        async with async_playwright() as pw:
            launch_kwargs: dict = {
                "headless": have_session,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            }
            if not have_session and real_chrome:
                # Use the real Chrome so Google OAuth works
                launch_kwargs["executable_path"] = real_chrome
                logger.info("Gerçek Chrome kullanılıyor: %s", real_chrome)

            browser = await pw.chromium.launch(**launch_kwargs)

            if have_session:
                storage_state = json.loads(_SESSION_FILE.read_text())
                context = await browser.new_context(
                    storage_state=storage_state,
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )
            else:
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                )

            page = await context.new_page()

            if not have_session:
                logger.info(
                    "Suno oturumu yok — tarayıcıda suno.com'a giriş yapın, "
                    "sonra terminalde Enter'a basın."
                )
                await page.goto(_SUNO_HOME)
                # Give the user time to log in interactively
                input("suno.com'da giriş yaptıktan sonra Enter'a basın: ")
            else:
                await page.goto(_SUNO_HOME)
                await page.wait_for_timeout(4000)

            # Extract JWT from Clerk session
            jwt = await page.evaluate(
                """async () => {
                    if (window.Clerk && window.Clerk.session) {
                        return await window.Clerk.session.getToken();
                    }
                    return null;
                }"""
            )

            # Save / refresh session cookies
            session_state = await context.storage_state()
            _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            _SESSION_FILE.write_text(json.dumps(session_state))
            logger.info("Suno oturumu kaydedildi: %s", _SESSION_FILE)

            await browser.close()

        if not jwt:
            raise RuntimeError(
                "Suno JWT alınamadı. suno.com'da tekrar giriş yapın ve "
                "config/suno_session.json dosyasını silin."
            )

        self._jwt = jwt
        return jwt

    async def _async_generate(self, style_prompt: str, suno_lyrics: str) -> str:
        """
        Submit generation by making the API call FROM WITHIN the browser page context.
        This avoids IP/cookie/CSRF issues and adapts to Suno API endpoint changes.
        """
        from playwright.async_api import async_playwright

        storage_state = json.loads(_SESSION_FILE.read_text())
        real_chrome = _find_real_browser()
        launch_kwargs: dict = {
            "headless": True,
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if real_chrome:
            launch_kwargs["executable_path"] = real_chrome

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(**launch_kwargs)
            context = await browser.new_context(
                storage_state=storage_state,
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()

            # Intercept the actual generate response to capture clip IDs
            captured: list[dict] = []

            async def on_response(response):
                if "generate" in response.url and response.status == 200:
                    try:
                        data = await response.json()
                        clips = data.get("clips", []) or data.get("data", [])
                        if clips:
                            captured.extend(clips)
                    except Exception:
                        pass

            page.on("response", on_response)

            await page.goto(_SUNO_HOME, wait_until="domcontentloaded")
            await page.wait_for_timeout(4000)

            # Get fresh JWT from the live page
            jwt = await page.evaluate(
                """async () => {
                    if (window.Clerk && window.Clerk.session) {
                        return await window.Clerk.session.getToken();
                    }
                    return null;
                }"""
            )
            if not jwt:
                await browser.close()
                raise RuntimeError(
                    "Suno JWT alınamadı. config/suno_session.json dosyasını silerek tekrar giriş yapın."
                )

            # Make the API call from within the browser (correct cookies + auth)
            result = await page.evaluate(
                """async ([style_prompt, suno_lyrics, jwt]) => {
                    const endpoints = [
                        "https://studio-api-prod.suno.com/api/generate/v2/",
                        "https://studio-api.suno.ai/api/generate/v2/",
                    ];
                    const payload = {
                        prompt: suno_lyrics,
                        mv: "chirp-v4",
                        title: "",
                        tags: style_prompt.slice(0, 200),
                        make_instrumental: false,
                    };
                    for (const url of endpoints) {
                        try {
                            const resp = await fetch(url, {
                                method: "POST",
                                headers: {
                                    "Content-Type": "application/json",
                                    "Authorization": "Bearer " + jwt,
                                },
                                body: JSON.stringify(payload),
                            });
                            const text = await resp.text();
                            return { status: resp.status, url, text };
                        } catch (e) {
                            continue;
                        }
                    }
                    return { status: 0, url: "", text: "all endpoints failed" };
                }""",
                [style_prompt, suno_lyrics, jwt],
            )

            await browser.close()

        logger.info("Suno generate yanıtı — status=%s url=%s", result["status"], result["url"])

        # Also check intercepted responses
        if captured:
            clip_id = captured[0]["id"]
            logger.info("Suno generation gönderildi — clip_id=%s (intercepted)", clip_id)
            return clip_id

        if result["status"] != 200:
            raise RuntimeError(
                f"Suno generate başarısız — HTTP {result['status']} | {result['text'][:300]}"
            )

        data = json.loads(result["text"])
        clips = data.get("clips", []) or data.get("data", [])
        if not clips:
            raise RuntimeError(f"Suno API yanıtında clip bulunamadı: {result['text'][:300]}")

        clip_id = clips[0]["id"]
        logger.info("Suno generation gönderildi — clip_id=%s", clip_id)
        return clip_id

    async def _async_get_status(self, task_id: str) -> dict:
        if not self._jwt:
            await self._ensure_jwt()

        headers = {"Authorization": f"Bearer {self._jwt}"}
        # Use the correct prod domain; also try legacy domain as fallback
        for base_url in (_API_BASE, "https://studio-api.suno.ai"):
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"{base_url}/api/feed/?ids={task_id}",
                        headers=headers,
                    )
                    if resp.status_code in (503, 404):
                        continue
                    resp.raise_for_status()
                    clips = resp.json()
                    break
            except httpx.HTTPStatusError:
                continue
        else:
            return {"status": "pending", "audio_url": None}

        if not clips:
            return {"status": "pending", "audio_url": None}

        clip = clips[0]
        status = clip.get("status", "pending")   # "submitted" | "queued" | "streaming" | "complete" | "error"
        audio_url = clip.get("audio_url")

        if status == "complete" and audio_url:
            return {"status": "complete", "audio_url": audio_url, "clip_id": task_id}
        if status in ("error", "failed"):
            return {"status": "failed", "audio_url": None}
        return {"status": "pending", "audio_url": None}

    async def _async_wait_and_download(self, task_id: str, destination: Path) -> Path:
        """Poll until complete, then download WAV."""
        deadline = time.monotonic() + _POLL_TIMEOUT_S
        logger.info("Suno clip %s bekleniyor (maks %d saniye)…", task_id, _POLL_TIMEOUT_S)

        while time.monotonic() < deadline:
            status = await self._async_get_status(task_id)
            if status["status"] == "complete":
                break
            if status["status"] == "failed":
                raise RuntimeError(f"Suno generation başarısız: clip_id={task_id}")
            logger.info("  clip %s: %s — %d saniye sonra tekrar denenecek",
                        task_id, status["status"], _POLL_INTERVAL_S)
            await asyncio.sleep(_POLL_INTERVAL_S)
        else:
            raise TimeoutError(f"Suno clip {task_id} {_POLL_TIMEOUT_S}s içinde tamamlanmadı.")

        audio_url = status["audio_url"]
        destination.parent.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient(timeout=300) as client:
            # 1) WAV doğrudan CDN'den dene
            wav_url = f"{_CDN_BASE}/{task_id}.wav"
            head_resp = await client.head(wav_url, follow_redirects=True)
            if head_resp.status_code == 200:
                dest_wav = destination.with_suffix(".wav")
                logger.info("WAV indiriliyor: %s", wav_url)
                async with client.stream("GET", wav_url, follow_redirects=True) as r:
                    r.raise_for_status()
                    with open(dest_wav, "wb") as f:
                        async for chunk in r.aiter_bytes(chunk_size=65536):
                            f.write(chunk)
                logger.info("WAV kaydedildi: %s", dest_wav)
                return dest_wav

            # 2) MP3 indir, ffmpeg ile 24-bit WAV'a dönüştür
            logger.info("WAV bulunamadı, MP3 indiriliyor ve dönüştürülüyor: %s", audio_url)
            mp3_dest = destination.with_suffix(".mp3")
            async with client.stream("GET", audio_url, follow_redirects=True) as r:
                r.raise_for_status()
                with open(mp3_dest, "wb") as f:
                    async for chunk in r.aiter_bytes(chunk_size=65536):
                        f.write(chunk)

        # ffmpeg: MP3 → 24-bit / 48 kHz WAV
        wav_dest = destination.with_suffix(".wav")
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", str(mp3_dest),
                "-acodec", "pcm_s24le",
                "-ar", "48000",
                "-ac", "2",
                str(wav_dest),
            ],
            capture_output=True,
        )
        if result.returncode == 0:
            mp3_dest.unlink(missing_ok=True)
            logger.info("WAV dönüştürme tamam: %s", wav_dest)
            return wav_dest

        logger.warning("ffmpeg dönüştürme başarısız, MP3 kullanılacak: %s", mp3_dest)
        return mp3_dest
