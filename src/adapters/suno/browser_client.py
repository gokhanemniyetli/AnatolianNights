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
import os
import re
import subprocess
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values

from src.config.settings import settings

logger = logging.getLogger(__name__)

_SESSION_FILE = Path("config/suno_session.json")
_ENV = dotenv_values(".env")
_SUNO_HOME = "https://suno.com"
_API_BASE = "https://studio-api-prod.suno.com"   # current prod domain
_CDN_BASE = "https://cdn1.suno.ai"

# Generation poll settings
_POLL_INTERVAL_S = 15       # seconds between status checks
_POLL_TIMEOUT_S = 600       # 10 minutes max wait
_GENERATE_RETRY_DELAYS_S = (120, 300)
_SIMPLE_PROMPT_MAX_CHARS = 2800
_CUSTOM_MODEL_FALLBACKS = ("chirp-v5", "chirp-v4-5", "chirp-auk", "chirp-v4")


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name) or _ENV.get(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        logger.warning("%s=%r geçersiz; varsayılan %s kullanılacak.", name, value, default)
        return default


def _model_candidates() -> list[str]:
    configured = (settings.suno.model_version or "").strip()
    candidates = [configured, *_CUSTOM_MODEL_FALLBACKS]
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)
    return result


_CAPTCHA_WAIT_TIMEOUT_S = _env_int("SUNO_CAPTCHA_WAIT_TIMEOUT_SECONDS", 900)


class _CaptchaNeedsHeadedMode(Exception):
    """Raised when a CAPTCHA is detected in headless mode; caller should retry headed."""

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


def _suno_profile_dir() -> Path:
    configured = (
        os.getenv("SUNO_CHROME_USER_DATA_DIR")
        or _ENV.get("SUNO_CHROME_USER_DATA_DIR")
        or "config/suno_browser_profile"
    )
    return Path(configured)


def _suno_headless() -> bool:
    value = os.getenv("SUNO_HEADLESS") or _ENV.get("SUNO_HEADLESS") or "true"
    return value.strip().lower() not in {"0", "false", "no", "off"}


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
        last_exc: Exception | None = None
        _headed_retry_done = False
        for attempt in range(len(_GENERATE_RETRY_DELAYS_S) + 1):
            try:
                force_headed = _headed_retry_done or not _suno_headless()
                return asyncio.run(self._async_generate_via_ui(style_prompt, suno_lyrics, _force_headed=force_headed))
            except _CaptchaNeedsHeadedMode:
                if _headed_retry_done:
                    raise RuntimeError(
                        "Suno CAPTCHA headed modda da çözülemedi. "
                        "Lütfen tarayıcıda manuel olarak çözün."
                    )
                logger.warning(
                    "Headless modda CAPTCHA algılandı — tarayıcı görünür modda yeniden başlatılıyor."
                )
                _headed_retry_done = True
                continue
            except RuntimeError as exc:
                last_exc = exc
                message = str(exc).lower()
                retryable = (
                    "http 503" in message
                    or "service_unavailable" in message
                    or "temporarily unavailable" in message
                )
                if not retryable or attempt >= len(_GENERATE_RETRY_DELAYS_S):
                    raise
                delay = _GENERATE_RETRY_DELAYS_S[attempt]
                logger.warning(
                    "Suno generate geçici hata verdi; %s saniye sonra tekrar denenecek "
                    "(attempt %s/%s): %s",
                    delay,
                    attempt + 2,
                    len(_GENERATE_RETRY_DELAYS_S) + 1,
                    exc,
                )
                time.sleep(delay)
        if last_exc:
            raise last_exc
        raise RuntimeError("Suno generate bilinmeyen nedenle tamamlanamadı.")

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
        profile_dir = _suno_profile_dir()
        real_chrome = _find_real_browser()

        async with async_playwright() as pw:
            if not have_session and profile_dir.exists():
                logger.info("Suno persistent profil deneniyor: %s", profile_dir)
                launch_kwargs: dict = {
                    "headless": True,
                    "args": [
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                    ],
                }
                if real_chrome:
                    launch_kwargs["executable_path"] = real_chrome

                context = await pw.chromium.launch_persistent_context(
                    user_data_dir=str(profile_dir),
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    **launch_kwargs,
                )
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(_SUNO_HOME)
                await page.wait_for_timeout(4000)
                jwt = await page.evaluate(
                    """async () => {
                        if (window.Clerk && window.Clerk.session) {
                            return await window.Clerk.session.getToken();
                        }
                        return null;
                    }"""
                )
                session_state = await context.storage_state()
                _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                _SESSION_FILE.write_text(json.dumps(session_state))
                await context.close()

                if jwt:
                    logger.info("Suno JWT persistent profilden alındı.")
                    self._jwt = jwt
                    return jwt

                logger.warning("Persistent profilden Suno JWT alınamadı; interaktif login denenecek.")

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

    async def _async_generate(self, style_prompt: str, suno_lyrics: str, attempt: int = 0) -> str:
        """
        Submit generation by making the API call FROM WITHIN the browser page context.
        This avoids IP/cookie/CSRF issues and adapts to Suno API endpoint changes.
        """
        from playwright.async_api import async_playwright

        if not _SESSION_FILE.exists():
            logger.info("Suno session dosyası yok; yeni oturum oluşturuluyor.")
            await self._ensure_jwt()

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
                logger.warning("Suno JWT alınamadı; UI fallback deneniyor.")
                if suno_lyrics and suno_lyrics.strip():
                    raise RuntimeError("Suno JWT alınamadı; custom lyrics mode UI fallback ile güvenli değil.")
                return await self._async_generate_via_ui(style_prompt, suno_lyrics)

            # Make the API call from within the browser (correct cookies + auth)
            result = await page.evaluate(
                """async ([style_prompt, suno_lyrics, jwt, model_versions]) => {
                    const endpoints = [
                        "https://studio-api-prod.suno.com/api/generate/v2/",
                        "https://studio-api.suno.ai/api/generate/v2/",
                    ];
                    const isSimpleMode = !suno_lyrics || !suno_lyrics.trim();
                    let last = { status: 0, url: "", text: "all endpoints failed", mv: "" };
                    for (const mv of model_versions) {
                        const payload = {
                            prompt: isSimpleMode ? style_prompt.slice(0, 2800) : suno_lyrics,
                            mv,
                            title: "",
                            tags: isSimpleMode ? "" : style_prompt.slice(0, 200),
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
                                last = { status: resp.status, url, text, mv };
                                if (
                                    resp.status === 400
                                    && text.toLowerCase().includes("selected model")
                                    && text.toLowerCase().includes("isn't valid")
                                ) {
                                    continue;
                                }
                                return last;
                            } catch (e) {
                                last = { status: 0, url, text: String(e), mv };
                                continue;
                            }
                        }
                    }
                    return last;
                }""",
                [style_prompt, suno_lyrics, jwt, _model_candidates()],
            )

            await browser.close()

        logger.info(
            "Suno generate yanıtı — status=%s url=%s body=%s",
            result["status"],
            f"{result['url']} mv={result.get('mv', '')}",
            result.get("text", "")[:500],
        )

        # Recover once when the stored browser session has gone stale.
        if (
            result["status"] == 422
            and "token_validation_failed" in result.get("text", "")
            and attempt == 0
        ):
            logger.warning("Suno token geçersiz; session yenilenip bir kez daha denenecek.")
            if _SESSION_FILE.exists():
                _SESSION_FILE.unlink()
            await self._ensure_jwt()
            return await self._async_generate(style_prompt, suno_lyrics, attempt=1)

        # Also check intercepted responses
        if captured:
            clip_id = captured[0]["id"]
            logger.info("Suno generation gönderildi — clip_id=%s (intercepted)", clip_id)
            return clip_id

        if result["status"] != 200:
            if (
                result["status"] == 422
                and "token_validation_failed" in result.get("text", "")
            ):
                if suno_lyrics and suno_lyrics.strip():
                    raise RuntimeError("Suno API token doğrulamasını reddetti; custom lyrics mode durduruldu.")
                logger.warning("Suno API token doğrulamasını reddetti; UI fallback deneniyor.")
                return await self._async_generate_via_ui(style_prompt, suno_lyrics)
            if (
                result["status"] == 400
                and "selected model isn't valid" in result.get("text", "")
            ):
                if suno_lyrics and suno_lyrics.strip():
                    raise RuntimeError("Suno API modeli custom lyrics mode için reddetti; sözler kaybolmasın diye durduruldu.")
                logger.warning("Suno API model değerini reddetti; UI fallback deneniyor.")
                return await self._async_generate_via_ui(style_prompt, suno_lyrics)
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

    async def _async_generate_via_ui(self, style_prompt: str, suno_lyrics: str = "", _force_headed: bool = False) -> str:
        """
        Generate through the real Suno Create UI.

        Suno's internal generate endpoint can reject direct fetch calls with
        token_validation_failed even when the browser session is valid. The UI
        path mirrors the user's normal Create flow and captures the successful
        v2-web response.
        """
        from playwright.async_api import async_playwright

        profile_dir = _suno_profile_dir()
        real_chrome = _find_real_browser()
        headless = False if _force_headed else _suno_headless()
        suno_lyrics = (suno_lyrics or "").strip()
        has_custom_lyrics = bool(suno_lyrics)

        async with async_playwright() as pw:
            launch_kwargs: dict = {
                "headless": headless,
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                ],
            }
            if real_chrome:
                launch_kwargs["executable_path"] = real_chrome

            context = await pw.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                **launch_kwargs,
            )
            page = context.pages[0] if context.pages else await context.new_page()

            loop = asyncio.get_running_loop()
            generate_future: asyncio.Future[dict] = loop.create_future()
            request_log: list[str] = []

            def on_request(request):
                if request.method != "POST" or "suno" not in request.url:
                    return
                try:
                    body = request.post_data or ""
                except Exception:
                    body = ""
                request_log.append(f"{request.method} {request.url} {body[:250]}")

            async def on_response(response):
                # Only intercept POST responses to the actual Suno generate endpoint
                if response.request.method != "POST":
                    return
                if "generate" not in response.url:
                    return
                # Ignore 204 No Content (preflight / CORS / unrelated POSTs)
                if response.status == 204:
                    return
                try:
                    text = await response.text()
                except Exception as exc:
                    if not generate_future.done():
                        generate_future.set_exception(exc)
                    return
                if response.status not in (200, 201):
                    if not generate_future.done():
                        generate_future.set_exception(
                            RuntimeError(f"Suno UI generate HTTP {response.status}: {text[:300]}")
                        )
                    return
                try:
                    data = json.loads(text)
                except json.JSONDecodeError as exc:
                    if not generate_future.done():
                        generate_future.set_exception(exc)
                    return
                clips = data.get("clips", []) or data.get("data", [])
                valid_clips = [
                    clip for clip in clips
                    if isinstance(clip, dict)
                    and clip.get("id")
                    and (
                        clip.get("audio_url")
                        or clip.get("audioUrl")
                        or clip.get("status") in {"submitted", "queued", "pending", "complete"}
                    )
                ]
                if not valid_clips:
                    return
                data["_captured_url"] = response.url
                if not generate_future.done():
                    generate_future.set_result(data)

            page.on("request", on_request)
            page.on("response", on_response)

            # Intercept Suno generate API calls and ALWAYS force make_instrumental=false.
            # Simple mode can produce instrumental tracks if the UI state is wrong or
            # Suno's React carries a stored preference. This route handler corrects the
            # payload at the network level before it reaches the server.
            async def _force_vocal_route(route, request):
                if "generate" in request.url and request.method == "POST":
                    try:
                        body_bytes = request.post_data_buffer
                        if body_bytes:
                            payload = json.loads(body_bytes)
                            was_instrumental = payload.get("make_instrumental")
                            payload["make_instrumental"] = False
                            logger.info(
                                "Suno generate payload (make_instrumental was=%s → false): %s",
                                was_instrumental,
                                str(payload)[:400],
                            )
                            await route.continue_(post_data=json.dumps(payload))
                            return
                        else:
                            logger.warning("Suno generate isteğinde body bulunamadı: %s", request.url)
                    except Exception as exc:
                        logger.warning("Suno route interception hatası: %s", exc)
                await route.continue_()

            await page.route("**/*", _force_vocal_route)

            try:
                await page.goto(f"{_SUNO_HOME}/create", wait_until="domcontentloaded")
                await page.wait_for_timeout(8000)
                await self._wait_for_manual_captcha_if_present(page, headless=headless)
                setup_state = await page.evaluate(
                    """async ([modelLabel, hasCustomLyrics]) => {
                    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
                    const visible = el => {
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return rect.width > 0 && rect.height > 0
                            && style.display !== "none"
                            && style.visibility !== "hidden";
                    };
                    const textOf = el => (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
                    const fireClick = el => {
                        el.scrollIntoView({ block: "center", inline: "center" });
                        for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
                            el.dispatchEvent(new MouseEvent(type, {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                            }));
                        }
                    };
                    const controls = () => [...document.querySelectorAll("button,[role=button]")]
                        .filter(visible);

                    const modeButton = controls().find(el =>
                        hasCustomLyrics ? /^advanced$/i.test(textOf(el)) : /^simple$/i.test(textOf(el))
                    );
                    if (modeButton) {
                        fireClick(modeButton);
                        await sleep(1200);
                    }

                    const lyricsVisible = [...document.querySelectorAll("textarea")]
                        .filter(visible)
                        .some(el => /lyric/i.test(el.placeholder || "") || /lyric/i.test(el.getAttribute("aria-label") || ""));
                    const simpleButton = controls().find(el => /^simple$/i.test(textOf(el)));
                    if (!hasCustomLyrics && lyricsVisible && simpleButton) {
                        fireClick(simpleButton);
                        await sleep(1200);
                    }
                    if (!hasCustomLyrics) {
                        // Ensure Instrumental toggle is OFF.
                        // Try by text label first, then by aria-label/title.
                        const instrumentalButton = controls().find(el =>
                            /instrumental/i.test(textOf(el)) ||
                            /instrumental/i.test(el.getAttribute("aria-label") || "") ||
                            /instrumental/i.test(el.getAttribute("title") || "")
                        );
                        const isInstrumentalOn = instrumentalButton && (
                            instrumentalButton.getAttribute("aria-pressed") === "true" ||
                            instrumentalButton.getAttribute("data-state") === "on" ||
                            instrumentalButton.getAttribute("data-state") === "checked" ||
                            instrumentalButton.getAttribute("aria-checked") === "true" ||
                            instrumentalButton.getAttribute("aria-selected") === "true" ||
                            /\bactive\b|\bselected\b|\bon\b|\bchecked\b/.test(instrumentalButton.className)
                        );
                        const instrumentalDebug = instrumentalButton
                            ? { found: true, outerHTML: instrumentalButton.outerHTML.slice(0, 300), isOn: isInstrumentalOn }
                            : { found: false };
                        if (instrumentalButton && isInstrumentalOn) {
                            fireClick(instrumentalButton);
                            await sleep(1000);
                        }
                        // Capture after-state for debug logging.
                        window.__instrumentalDebug = instrumentalDebug;
                        window.__instrumentalAfter = instrumentalButton ? {
                            aria_pressed: instrumentalButton.getAttribute("aria-pressed"),
                            data_state: instrumentalButton.getAttribute("data-state"),
                            aria_checked: instrumentalButton.getAttribute("aria-checked"),
                            className: instrumentalButton.className.slice(0, 120),
                        } : null;
                    }

                    const modelControls = controls().filter(el => /v[0-9]|model|chirp/i.test(textOf(el)));
                    for (const control of modelControls) {
                        fireClick(control);
                        await sleep(700);
                        const option = [...document.querySelectorAll("[role=option],button,[role=button],[role=menuitem],li,div")]
                            .filter(visible)
                            .find(el => textOf(el).toLowerCase().includes(modelLabel.toLowerCase()));
                        if (option) {
                            fireClick(option);
                            await sleep(1000);
                            return { ok: true, mode: hasCustomLyrics ? "advanced" : "simple", model: modelLabel,
                                     instrumental_debug: window.__instrumentalDebug,
                                     instrumental_after: window.__instrumentalAfter };
                        }
                    }
                    const selectedModel = controls().find(el => textOf(el).toLowerCase().includes(modelLabel.toLowerCase()));
                    if (selectedModel) {
                        return { ok: true, mode: hasCustomLyrics ? "advanced" : "simple", model: modelLabel,
                                 instrumental_debug: window.__instrumentalDebug,
                                 instrumental_after: window.__instrumentalAfter };
                    }
                    return { ok: true, mode: hasCustomLyrics ? "advanced" : "simple", model: "unchanged",
                             instrumental_debug: window.__instrumentalDebug,
                             instrumental_after: window.__instrumentalAfter };
                    }""",
                    ["v5.5", has_custom_lyrics],
                )
                logger.info("Suno UI setup: %s", setup_state)
                if setup_state.get("model") not in {"v5.5", "unchanged"}:
                    raise RuntimeError(f"Suno UI v5.5 modeli doğrulanamadı: {setup_state}")
                if setup_state.get("model") == "unchanged":
                    logger.warning(
                        "Suno UI model seçimi doğrulanamadı; mevcut seçili modelle devam ediliyor: %s",
                        setup_state,
                    )

                # --- Login check ---
                textarea_count = await page.evaluate(
                    """() => {
                        const visible = el => {
                            const rect = el.getBoundingClientRect();
                            const style = getComputedStyle(el);
                            return rect.width > 0 && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        return [...document.querySelectorAll("textarea")].filter(visible).length;
                    }"""
                )
                if textarea_count == 0:
                    if headless:
                        raise RuntimeError(
                            "Suno oturumu geçersiz veya giriş yapılmamış. "
                            "SUNO_HEADLESS=false ortam değişkeniyle komutu tekrar çalıştırın "
                            "ve açılan Chrome penceresinde suno.com'a giriş yapın."
                        )
                    logger.warning(
                        "Suno'ya giriş yapılmamış — Chrome penceresi açık, lütfen suno.com'a giriş yapın."
                    )
                    _loop = asyncio.get_running_loop()
                    try:
                        await _loop.run_in_executor(
                            None,
                            input,
                            "Suno'ya giriş yaptıktan sonra burada Enter'a basın: ",
                        )
                    except EOFError as exc:
                        raise RuntimeError(
                            "Suno oturumu geçersiz ve stdin kapalı. "
                            "Komutu interaktif terminalde SUNO_HEADLESS=false ile çalıştırın."
                        ) from exc
                    await page.goto(f"{_SUNO_HOME}/create", wait_until="domcontentloaded")
                    await page.wait_for_timeout(6000)
                    await self._wait_for_manual_captcha_if_present(page, headless=headless)
                    setup_state = await page.evaluate(
                        """async ([modelLabel, hasCustomLyrics]) => {
                        const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
                        const visible = el => {
                            const rect = el.getBoundingClientRect();
                            const style = getComputedStyle(el);
                            return rect.width > 0 && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const textOf = el => (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
                        const fireClick = el => {
                            el.scrollIntoView({ block: "center", inline: "center" });
                            for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
                                el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                            }
                        };
                        const controls = () => [...document.querySelectorAll("button,[role=button]")].filter(visible);
                        const modeButton = controls().find(el =>
                            hasCustomLyrics ? /^advanced$/i.test(textOf(el)) : /^simple$/i.test(textOf(el))
                        );
                        if (modeButton) { fireClick(modeButton); await sleep(1200); }
                        if (!hasCustomLyrics) {
                            // Ensure Instrumental toggle is OFF.
                            const instrumentalButton = controls().find(el =>
                                /instrumental/i.test(textOf(el)) ||
                                /instrumental/i.test(el.getAttribute("aria-label") || "") ||
                                /instrumental/i.test(el.getAttribute("title") || "")
                            );
                            const isInstrumentalOn = instrumentalButton && (
                                instrumentalButton.getAttribute("aria-pressed") === "true" ||
                                instrumentalButton.getAttribute("data-state") === "on" ||
                                instrumentalButton.getAttribute("data-state") === "checked" ||
                                instrumentalButton.getAttribute("aria-checked") === "true" ||
                                instrumentalButton.getAttribute("aria-selected") === "true" ||
                                /\bactive\b|\bselected\b|\bon\b|\bchecked\b/.test(instrumentalButton.className)
                            );
                            window.__instrumentalDebug = instrumentalButton
                                ? { found: true, outerHTML: instrumentalButton.outerHTML.slice(0, 300), isOn: isInstrumentalOn }
                                : { found: false };
                            if (instrumentalButton && isInstrumentalOn) {
                                fireClick(instrumentalButton);
                                await sleep(1000);
                            }
                        }
                        return { ok: true, mode: hasCustomLyrics ? "advanced" : "simple", model: "unchanged",
                                 instrumental_debug: window.__instrumentalDebug };
                        }""",
                        ["v5.5", has_custom_lyrics],
                    )
                    logger.info("Suno UI setup (sonrası): %s", setup_state)
                # --- Login check end ---

                form_state = await page.evaluate(
                    """([stylePrompt, lyrics]) => {
                        const visible = el => {
                            const rect = el.getBoundingClientRect();
                            const style = getComputedStyle(el);
                            return rect.width > 0 && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const textareas = [...document.querySelectorAll("textarea")]
                            .filter(visible)
                            .sort((a, b) => a.getBoundingClientRect().y - b.getBoundingClientRect().y);
                        const setValue = (target, value) => {
                            target.scrollIntoView({ block: "center" });
                            target.focus();
                            const setter = Object.getOwnPropertyDescriptor(
                                window.HTMLTextAreaElement.prototype,
                                "value"
                            ).set;
                            setter.call(target, value);
                            target.dispatchEvent(new InputEvent("input", {
                                bubbles: true,
                                inputType: "insertText",
                                data: value,
                            }));
                            target.dispatchEvent(new Event("change", { bubbles: true }));
                        };
                        if (lyrics && lyrics.trim()) {
                            if (textareas.length < 2) {
                                return {
                                    ok: false,
                                    reason: "advanced lyrics/style fields not found",
                                    textareaCount: textareas.length,
                                    placeholders: textareas.map(e => e.placeholder || e.getAttribute("aria-label") || "")
                                };
                            }
                            setValue(textareas[0], lyrics);
                            setValue(textareas[1], stylePrompt);
                            return {
                                ok: true,
                                mode: "advanced",
                                placeholders: textareas.slice(0, 2).map(e => e.placeholder || e.getAttribute("aria-label") || ""),
                            };
                        }
                        const lyricsFields = textareas.filter(
                            e => /lyric/i.test(e.placeholder || "") || /lyric/i.test(e.getAttribute("aria-label") || "")
                        );
                        if (lyricsFields.length || textareas.length !== 1) {
                            return {
                                ok: false,
                                reason: "simple mode not verified",
                                textareaCount: textareas.length,
                                placeholders: textareas.map(e => e.placeholder || e.getAttribute("aria-label") || "")
                            };
                        }
                        const target = textareas[0];
                        if (!target) {
                            return { ok: false, reason: "prompt textarea not found" };
                        }
                        setValue(target, stylePrompt);
                        return { ok: true, placeholder: target.placeholder, value: target.value };
                        }""",
                    [style_prompt[:_SIMPLE_PROMPT_MAX_CHARS], suno_lyrics],
                )
                if not form_state.get("ok"):
                    raise RuntimeError(f"Suno UI prompt alanı bulunamadı: {form_state}")
                if not has_custom_lyrics:
                    await page.locator("textarea:visible").first.fill(
                        style_prompt[:_SIMPLE_PROMPT_MAX_CHARS]
                    )
                await page.wait_for_timeout(800)

                await page.wait_for_timeout(1500)
                create_target = await page.evaluate(
                    """() => {
                        const visible = el => {
                            const rect = el.getBoundingClientRect();
                            const style = getComputedStyle(el);
                            return rect.width > 0 && rect.height > 0
                                && style.display !== "none"
                                && style.visibility !== "hidden";
                        };
                        const textOf = el => (el.innerText || el.textContent || el.getAttribute("aria-label") || "").trim();
                        const candidates = [...document.querySelectorAll("button,[role=button],div")]
                            .filter(visible)
                            .filter(el => /^Create$/i.test(textOf(el)) || /Create song/i.test(textOf(el)))
                            .map(el => {
                                const rect = el.getBoundingClientRect();
                                return {
                                    x: rect.x,
                                    y: rect.y,
                                    width: rect.width,
                                    height: rect.height,
                                    area: rect.width * rect.height,
                                    disabled: Boolean(el.disabled) || el.getAttribute("aria-disabled") === "true",
                                    text: textOf(el),
                                };
                            })
                            .filter(item => !item.disabled);
                        candidates.sort((a, b) => b.area - a.area);
                        return { target: candidates[0] || null, candidates: candidates.slice(0, 8) };
                    }"""
                )
                logger.debug("Suno Create candidates: %s", create_target)
                create_target = create_target.get("target") if create_target else None
                if not create_target:
                    raise RuntimeError("Suno UI Create butonu bulunamadı.")
                await self._wait_for_manual_captcha_if_present(page, headless=headless)

                data = None
                for click_attempt in range(2):
                    await page.mouse.click(
                        create_target["x"] + create_target["width"] / 2,
                        create_target["y"] + create_target["height"] / 2,
                    )
                    try:
                        data = await asyncio.wait_for(asyncio.shield(generate_future), timeout=240)
                        break
                    except TimeoutError as exc:
                        if await self._is_captcha_visible(page) and click_attempt == 0:
                            await self._wait_for_manual_captcha_if_present(page, force_prompt=True, headless=headless)
                            continue

                        screenshot_path = Path("/private/tmp/suno_generate_timeout.png")
                        await page.screenshot(path=str(screenshot_path), full_page=True)
                        visible_text = await page.locator("body").inner_text(timeout=5000)
                        raise TimeoutError(
                            "Suno generate API yanıtı gelmedi. "
                            f"Screenshot: {screenshot_path}. "
                            f"POST log: {request_log[-10:]}. "
                            f"Visible UI: {visible_text[:800]}"
                        ) from exc
            finally:
                session_state = await context.storage_state()
                _SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
                _SESSION_FILE.write_text(json.dumps(session_state))
                await context.close()

        if data is None:
            raise RuntimeError("Suno UI generate tamamlanamadı.")

        clips = data.get("clips", []) or data.get("data", [])
        if not clips:
            raise RuntimeError(f"Suno UI generate yanıtında clip bulunamadı: {str(data)[:300]}")
        clip_id = clips[0]["id"]
        logger.info("Suno UI generation gönderildi — clip_id=%s url=%s", clip_id, data.get("_captured_url", ""))
        return clip_id

    async def _is_captcha_visible(self, page) -> bool:
        return bool(
            await page.evaluate(
                """() => {
                const visible = el => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0
                        && style.display !== "none"
                        && style.visibility !== "hidden";
                };
                const hcaptchaFrame = [...document.querySelectorAll("iframe")]
                    .some(frame => /hcaptcha/i.test(frame.src || frame.title || frame.name || ""));
                const bodyText = (document.body?.innerText || "").toLowerCase();
                // "challenge" is too broad (Suno's own page content may contain it).
                // Only match very specific CAPTCHA phrases.
                const challengeText = bodyText.includes("hcaptcha")
                    || bodyText.includes("verify you are human")
                    || bodyText.includes("verify that you are human");
                return hcaptchaFrame || challengeText
                    || Boolean([...document.querySelectorAll("[data-hcaptcha-widget-id], .h-captcha")]
                        .find(visible));
                }"""
            )
        )

    async def _wait_for_manual_captcha_if_present(self, page, force_prompt: bool = False, headless: bool = True) -> None:
        if not force_prompt and not await self._is_captcha_visible(page):
            return

        screenshot_path = Path("/private/tmp/suno_captcha_wait.png")
        await page.screenshot(path=str(screenshot_path), full_page=True)

        if headless:
            # Browser is invisible — raise so caller can restart in headed mode.
            logger.warning(
                "Headless modda CAPTCHA algılandı. Tarayıcı görünür modda yeniden başlatılıyor. "
                "Ekran görüntüsü: %s",
                screenshot_path,
            )
            try:
                subprocess.run(["open", str(screenshot_path)], check=False)
            except Exception:
                pass
            raise _CaptchaNeedsHeadedMode()

        logger.warning(
            "Suno CAPTCHA bekliyor. Tarayıcıda CAPTCHA'yı elle çözün; "
            "ekran görüntüsü: %s",
            screenshot_path,
        )

        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                None,
                input,
                "Suno CAPTCHA'yı tarayıcıda çözdükten sonra burada Enter'a basın: ",
            )
        except EOFError as exc:
            raise RuntimeError(
                "Suno CAPTCHA manuel çözüm bekliyor, ancak komut interaktif terminalde "
                "çalışmıyor. Komutu terminalden tekrar çalıştırın."
            ) from exc

        deadline = time.monotonic() + _CAPTCHA_WAIT_TIMEOUT_S
        while await self._is_captcha_visible(page):
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "Suno CAPTCHA manuel çözümden sonra hâlâ görünür durumda. "
                    f"Screenshot: {screenshot_path}"
                )
            logger.info("CAPTCHA hâlâ görünür; çözümün Suno UI'a yansıması bekleniyor.")
            await page.wait_for_timeout(3000)

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
        suno_lyrics = self._extract_suno_lyrics(clip)

        if status == "complete" and audio_url:
            return {
                "status": "complete",
                "audio_url": audio_url,
                "clip_id": task_id,
                "suno_title": self._extract_suno_title(clip),
                "suno_lyrics": suno_lyrics,
            }
        if status in ("error", "failed"):
            return {
                "status": "failed",
                "audio_url": None,
                "suno_title": self._extract_suno_title(clip),
                "suno_lyrics": suno_lyrics,
            }
        return {
            "status": "pending",
            "audio_url": None,
            "suno_title": self._extract_suno_title(clip),
            "suno_lyrics": suno_lyrics,
        }

    @staticmethod
    def _extract_suno_title(clip: dict) -> str:
        title = clip.get("title")
        return title.strip() if isinstance(title, str) and title.strip() else ""

    @staticmethod
    def _extract_suno_lyrics(clip: dict) -> str:
        metadata = clip.get("metadata") or {}
        for value in (
            clip.get("lyrics"),
            clip.get("lyric"),
            metadata.get("lyrics"),
            metadata.get("lyric"),
            metadata.get("prompt"),
        ):
            if isinstance(value, str):
                lyrics = BrowserSunoClient._clean_suno_lyrics(value)
                if lyrics:
                    return lyrics
        return ""

    @staticmethod
    def _clean_suno_lyrics(value: str) -> str:
        text = value.strip()
        if not text:
            return ""
        lower = text.lower()
        polluted_markers = (
            "simple_prompt",
            "bilibili.com",
            "助手",
            "当然可以",
            "```json",
            "write the lyrics",
            "do not include",
            "suno",
        )
        if any(marker in lower for marker in polluted_markers):
            return ""
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith("```")
        ]
        content_lines = [line for line in lines if not re.match(r"^\[[^\]]+\]$", line)]
        if len(content_lines) < 4:
            return ""
        return "\n".join(lines)

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
