"""
YouTube Studio web uploader.

This is a browser fallback for cases where the YouTube Data API rejects an
upload but the same account can upload through studio.youtube.com.
"""

import json
import logging
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)


class YouTubeStudioUploader:
    def __init__(
        self,
        profile_dir: str | Path = "config/youtube_browser_profile",
        headless: bool = False,
        timeout_ms: int = 900_000,
    ):
        self.profile_dir = Path(profile_dir)
        self.headless = headless
        self.timeout_ms = timeout_ms

    def upload_video(
        self,
        video_path: Path,
        title: str,
        description: str,
        thumbnail_path: Path | None = None,
        add_end_screen: bool = False,
        playlist_title: str | None = None,
        related_video_id: str | None = None,
        related_video_title: str | None = None,
    ) -> str:
        video_path = Path(video_path).resolve()
        if not video_path.exists():
            raise FileNotFoundError(video_path)

        with sync_playwright() as pw:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            context = pw.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                video_id = self._upload_with_page(
                    page=page,
                    video_path=video_path,
                    title=title,
                    description=description,
                    thumbnail_path=thumbnail_path,
                    add_end_screen=add_end_screen,
                    playlist_title=playlist_title,
                    related_video_id=related_video_id,
                    related_video_title=related_video_title,
                )
                self._save_state(context)
                return video_id
            finally:
                context.close()

    def set_related_video(
        self,
        short_video_id: str,
        related_video_id: str,
        related_video_title: str = "",
    ) -> None:
        """Set a Short's related video from the YouTube Studio edit page."""
        if not short_video_id or not related_video_id:
            return

        with sync_playwright() as pw:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            context = pw.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                logger.info(
                    "Opening YouTube Studio edit page for Short related video: %s -> %s",
                    short_video_id,
                    related_video_id,
                )
                page.goto(
                    f"https://studio.youtube.com/video/{short_video_id}/edit",
                    wait_until="domcontentloaded",
                )
                self._wait_for_login_if_needed(page)
                self._set_related_video_from_edit_page(
                    page,
                    related_video_id,
                    related_video_title,
                )
                self._save_state(context)
            finally:
                context.close()

    def add_end_screen(self, video_id: str) -> None:
        """Add a 1 video + 1 subscribe end screen from Studio."""
        if not video_id:
            return

        with sync_playwright() as pw:
            self.profile_dir.mkdir(parents=True, exist_ok=True)
            context = pw.chromium.launch_persistent_context(
                str(self.profile_dir),
                headless=self.headless,
                viewport={"width": 1440, "height": 1000},
                accept_downloads=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(self.timeout_ms)

            try:
                logger.info("Opening YouTube Studio details page for end screen: %s", video_id)
                page.goto(
                    f"https://studio.youtube.com/video/{video_id}/edit",
                    wait_until="domcontentloaded",
                )
                self._wait_for_login_if_needed(page)
                self._add_end_screen_from_details_page(page)
                self._save_state(context)
            finally:
                context.close()

    def _upload_with_page(
        self,
        page,
        video_path: Path,
        title: str,
        description: str,
        thumbnail_path: Path | None,
        add_end_screen: bool,
        playlist_title: str | None,
        related_video_id: str | None,
        related_video_title: str | None,
    ) -> str:
        logger.info("Opening YouTube Studio web uploader...")
        page.goto("https://studio.youtube.com", wait_until="domcontentloaded")
        self._open_upload_dialog(page)

        logger.info("Selecting video file: %s", video_path)
        page.locator("input[type=file]").first.set_input_files(str(video_path))

        self._fill_details(page, title, description)
        self._set_not_made_for_kids(page)
        if related_video_id:
            self._try_set_related_video(page, related_video_id, related_video_title or title)

        if thumbnail_path and thumbnail_path.exists():
            self._try_set_thumbnail(page, thumbnail_path)
        if playlist_title:
            self._try_set_playlist(page, playlist_title)

        self._advance_to_visibility(page, add_end_screen=add_end_screen)
        self._set_public(page)
        self._publish(page)
        video_id = self._extract_video_id(page)
        logger.info("YouTube Studio upload completed: %s", video_id)
        return video_id

    def _open_upload_dialog(self, page) -> None:
        self._wait_for_login_if_needed(page)

        if page.locator("input[type=file]").count():
            return

        create_patterns = [
            re.compile(r"^(Create|Oluştur)$", re.I),
            re.compile(r"(Create|Oluştur)", re.I),
        ]
        upload_patterns = [
            re.compile(r"(Upload videos|Video yükle|Videoları yükle)", re.I),
            re.compile(r"(Upload|Yükle)", re.I),
        ]

        for pattern in create_patterns:
            try:
                page.get_by_role("button", name=pattern).click(timeout=15_000)
                break
            except PlaywrightTimeoutError:
                continue

        for pattern in upload_patterns:
            try:
                page.get_by_text(pattern).click(timeout=15_000)
                page.locator("input[type=file]").first.wait_for(state="attached", timeout=60_000)
                return
            except PlaywrightTimeoutError:
                continue

        screenshot = "/private/tmp/youtube_studio_open_upload_failed.png"
        page.screenshot(path=screenshot, full_page=True)
        raise TimeoutError(f"YouTube Studio upload dialog could not be opened. Screenshot: {screenshot}")

    def _wait_for_login_if_needed(self, page) -> None:
        login_markers = [
            "accounts.google.com",
            "ServiceLogin",
        ]
        on_login_page = any(marker in page.url for marker in login_markers)
        if not on_login_page:
            try:
                on_login_page = page.get_by_text(re.compile(r"Sign in|Oturum aç", re.I)).count() > 0
            except Exception:
                on_login_page = False

        if not on_login_page:
            return

        logger.info(
            "YouTube Studio profile is not signed in. Complete Google login in the opened browser; waiting..."
        )
        try:
            page.wait_for_url(re.compile(r"https://studio\.youtube\.com.*"), timeout=900_000)
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
        except PlaywrightTimeoutError as exc:
            screenshot = "/private/tmp/youtube_studio_login_timeout.png"
            page.screenshot(path=screenshot, full_page=True)
            raise TimeoutError(f"Google login was not completed. Screenshot: {screenshot}") from exc

    def _fill_details(self, page, title: str, description: str) -> None:
        logger.info("Filling title and description...")
        boxes = page.locator("ytcp-social-suggestions-textbox #textbox")
        boxes.first.wait_for(timeout=180_000)
        self._replace_textbox(boxes.nth(0), title[:100])
        if boxes.count() > 1:
            self._replace_textbox(boxes.nth(1), description[:5000])

    def _replace_textbox(self, locator, text: str) -> None:
        locator.click()
        locator.press("Meta+A")
        locator.press("Backspace")
        locator.fill(text)

    def _set_not_made_for_kids(self, page) -> None:
        patterns = [
            re.compile(r"No,.*not made for kids", re.I),
            re.compile(r"Hayır,.*çocuklara özel değil", re.I),
            re.compile(r"Çocuklara özel değil", re.I),
        ]
        for pattern in patterns:
            try:
                page.get_by_text(pattern).click(timeout=10_000)
                return
            except PlaywrightTimeoutError:
                continue

    def _try_set_thumbnail(self, page, thumbnail_path: Path) -> None:
        # Custom thumbnail permission can be unavailable for small/new channels.
        try:
            inputs = page.locator("input[type=file]")
            if inputs.count() > 1:
                inputs.nth(1).set_input_files(str(thumbnail_path.resolve()), timeout=10_000)
        except Exception as exc:
            logger.warning("Web thumbnail selection skipped: %s", exc)

    def _try_set_playlist(self, page, playlist_title: str) -> None:
        logger.info("Trying to select playlist: %s", playlist_title)
        try:
            self._expand_details(page)
            self._scroll_upload_dialog(page, 1800)
            label = page.get_by_text(re.compile(r"(Playlists|Oynatma listeleri)", re.I)).first
            label.wait_for(timeout=20_000)
            label.scroll_into_view_if_needed(timeout=5_000)
            if not self._click_playlist_select(page):
                logger.warning("Playlist selector was not found; skipping.")
                return
            self._choose_playlist(page, playlist_title)
            logger.info("Playlist step completed.")
        except Exception as exc:
            logger.warning("Playlist step skipped: %s", exc)

    def _click_playlist_select(self, page) -> bool:
        clicked = page.evaluate(
            """
            () => {
              const labelRe = /(Playlists|Oynatma listeleri)/i;
              const roots = [...document.querySelectorAll('*')]
                .filter((el) => labelRe.test(el.textContent || ''));

              for (const root of roots) {
                let node = root;
                for (let depth = 0; node && depth < 10; depth += 1, node = node.parentElement) {
                  const controls = [...node.querySelectorAll('ytcp-dropdown-trigger, tp-yt-paper-dropdown-menu, ytcp-select, [role="button"], button')];
                  const control = controls.find((candidate) => {
                    const text = (candidate.innerText || candidate.textContent || candidate.getAttribute('aria-label') || '').trim();
                    const disabled = candidate.disabled || candidate.getAttribute('aria-disabled') === 'true';
                    return !disabled && /(Select|Seç|Playlists|Oynatma listeleri)/i.test(text);
                  });
                  if (control) {
                    control.click();
                    return true;
                  }
                }
              }
              return false;
            }
            """
        )
        return bool(clicked)

    def _choose_playlist(self, page, playlist_title: str) -> None:
        title_re = re.compile(re.escape(playlist_title), re.I)
        try:
            page.get_by_text(title_re).first.click(timeout=15_000)
        except PlaywrightTimeoutError:
            logger.warning("Playlist '%s' was not visible in Studio dialog.", playlist_title)
            self._dismiss_open_dialog(page)
            return

        for name in [r"Done", r"Bitti", r"Save", r"Kaydet", r"Apply", r"Uygula"]:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).click(timeout=5_000)
                page.wait_for_timeout(1_000)
                return
            except PlaywrightTimeoutError:
                continue

    def _try_set_related_video(self, page, video_id: str, video_title: str) -> None:
        logger.info("Trying to set Short related video: %s", video_id)
        try:
            self._expand_details(page)
            self._scroll_upload_dialog(page, 1800)
            label = page.get_by_text(re.compile(r"(Related video|İlgili video)", re.I)).first
            label.wait_for(timeout=20_000)
            label.scroll_into_view_if_needed(timeout=5_000)
            if not self._click_related_video_select(page):
                logger.warning("Related video select button was not found; skipping.")
                return

            self._search_and_choose_related_video(page, video_id, video_title)
            self._save_related_video(page)
            logger.info("Related video step completed.")
        except Exception as exc:
            logger.warning("Related video step skipped: %s", exc)

    def _set_related_video_from_edit_page(
        self,
        page,
        video_id: str,
        video_title: str,
    ) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
            page.get_by_text(re.compile(r"(Related video|İlgili video)", re.I)).first.wait_for(
                timeout=90_000
            )
            self._scroll_to_related_video(page)
            if not self._click_related_video_edit(page):
                screenshot = "/private/tmp/youtube_studio_related_video_button_failed.png"
                page.screenshot(path=screenshot, full_page=True)
                raise TimeoutError(f"Related video edit button not found. Screenshot: {screenshot}")

            self._raise_if_related_video_verification_required(page)
            self._search_and_choose_related_video(page, video_id, video_title)
            self._raise_if_related_video_verification_required(page)
            self._save_related_video(page)
            self._save_video_edit(page)
            page.wait_for_timeout(3_000)
            if not self._related_video_card_has_value(page):
                self._raise_if_related_video_verification_required(page)
                screenshot = "/private/tmp/youtube_studio_related_video_still_empty.png"
                page.screenshot(path=screenshot, full_page=True)
                raise TimeoutError(f"Related video is still empty. Screenshot: {screenshot}")
            logger.info("Related video saved for Short: %s", video_id)
        except PermissionError:
            raise
        except Exception as exc:
            screenshot = "/private/tmp/youtube_studio_related_video_failed.png"
            try:
                page.screenshot(path=screenshot, full_page=True)
            except Exception:
                pass
            raise TimeoutError(f"Could not set related video. Screenshot: {screenshot}") from exc

    def _raise_if_related_video_verification_required(self, page) -> None:
        verify_re = re.compile(
            r"(verify your phone number|telefon numaranızı doğrulayın|daha fazla özelliğe erişin|access more features)",
            re.I,
        )
        try:
            text = page.locator("body").inner_text(timeout=2_000)
        except Exception:
            return
        if verify_re.search(text):
            screenshot = "/private/tmp/youtube_studio_related_video_verification_required.png"
            try:
                page.screenshot(path=screenshot, full_page=True)
            except Exception:
                pass
            self._dismiss_open_dialog(page)
            raise PermissionError(
                "YouTube Studio requires phone verification before Shorts can be linked "
                f"to related long videos. Screenshot: {screenshot}"
            )

    def _scroll_to_related_video(self, page) -> None:
        page.evaluate(
            """
            () => {
              const labelRe = /(Related video|İlgili video)/i;
              const el = [...document.querySelectorAll('*')]
                .filter((node) => {
                  const text = (node.innerText || node.textContent || '').trim();
                  return text.length < 80 && labelRe.test(text);
                })
                .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
              if (el) el.scrollIntoView({block: 'center', inline: 'nearest'});
            }
            """
        )
        page.wait_for_timeout(1_000)

    def _click_related_video_edit(self, page) -> bool:
        clicked = page.evaluate(
            """
            () => {
              const direct = document.querySelector('#linked-video-editor-link');
              if (direct) {
                direct.scrollIntoView({block: 'center', inline: 'center'});
                direct.click();
                return true;
              }

              const labelRe = /(Related video|İlgili video)/i;
              const forbiddenRe = /(Visibility|Görünürlük|Restrictions|Kısıtlamalar|Subtitles|Altyazılar)/i;
              const labels = [...document.querySelectorAll('*')]
                .filter((el) => {
                  const text = (el.innerText || el.textContent || '').trim();
                  const box = el.getBoundingClientRect();
                  return text.length < 80 && box.width > 0 && box.height > 0 && labelRe.test(text);
                });

              for (const label of labels) {
                const labelBox = label.getBoundingClientRect();
                const controls = [...document.querySelectorAll(
                  'ytcp-icon-button, tp-yt-paper-icon-button, yt-icon-button, button, [role="button"]'
                )]
                  .map((button) => ({button, box: button.getBoundingClientRect()}))
                  .filter(({button, box}) => {
                    const text = (button.innerText || button.textContent || button.getAttribute('aria-label') || '').trim();
                    const disabled = button.disabled || button.getAttribute('aria-disabled') === 'true';
                    const html = (button.getAttribute('icon') || button.innerHTML || '').toLowerCase();
                    const centerY = box.top + (box.height / 2);
                    const nearLabel = centerY >= labelBox.top - 60 && centerY <= labelBox.bottom + 70;
                    const rightOfLabel = box.left > labelBox.left + 80;
                    const visible = box.width > 0 && box.height > 0;
                    const looksEditable = !text || /(Edit|Düzenle|Select|Seç|Choose|Add|Ekle)/i.test(text) || /(edit|pencil|create)/i.test(html);
                    return visible && !disabled && nearLabel && rightOfLabel && looksEditable;
                  })
                  .sort((a, b) => b.box.right - a.box.right);
                if (controls.length) {
                  controls[0].button.scrollIntoView({block: 'center', inline: 'center'});
                  controls[0].button.click();
                  return true;
                }

                for (let node = label; node && node !== document.body; node = node.parentElement) {
                  const box = node.getBoundingClientRect();
                  const text = (node.innerText || node.textContent || '').trim();
                  if (forbiddenRe.test(text.replace(labelRe, ''))) continue;
                  if (box.width >= 250 && box.height >= 45 && box.width <= 520 && box.height <= 130 && labelRe.test(text)) {
                    const buttons = [...node.querySelectorAll(
                      'ytcp-icon-button, tp-yt-paper-icon-button, yt-icon-button, button, [role="button"]'
                    )].reverse();
                    const editButton = buttons.find((button) => {
                      const buttonBox = button.getBoundingClientRect();
                      const text = (button.innerText || button.textContent || button.getAttribute('aria-label') || '').trim();
                      const html = (button.getAttribute('icon') || button.innerHTML || '').toLowerCase();
                      const disabled = button.disabled || button.getAttribute('aria-disabled') === 'true';
                      return !disabled && buttonBox.width > 0 && buttonBox.height > 0
                        && (!text || /(Edit|Düzenle|Select|Seç|Choose|Add|Ekle)$/i.test(text) || /(edit|pencil|create)/i.test(html));
                    });
                    if (editButton) {
                      editButton.scrollIntoView({block: 'center', inline: 'center'});
                      editButton.click();
                      return true;
                    }
                  }
                }
              }
              return false;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(1_500)
        return bool(clicked)

    def _related_video_card_has_value(self, page) -> bool:
        return bool(
            page.evaluate(
                """
                () => {
                  const labelRe = /(Related video|İlgili video)/i;
                  const emptyRe = /^(None|Hiçbiri|Yok)$/i;
                  const forbiddenRe = /(Visibility|Görünürlük|Restrictions|Kısıtlamalar|Subtitles|Altyazılar)/i;
                  const label = [...document.querySelectorAll('*')]
                    .filter((el) => {
                      const text = (el.innerText || el.textContent || '').trim();
                      const box = el.getBoundingClientRect();
                      return text.length < 80 && box.width > 0 && box.height > 0 && labelRe.test(text);
                    })[0];
                  if (!label) return false;
                  for (let node = label; node && node !== document.body; node = node.parentElement) {
                    const box = node.getBoundingClientRect();
                    const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
                    if (box.width >= 250 && box.height >= 45 && box.width <= 520 && box.height <= 130 && labelRe.test(text) && !forbiddenRe.test(text.replace(labelRe, ''))) {
                      const value = text.replace(labelRe, '').replace(/[?？]/g, '').trim();
                      return Boolean(value) && !emptyRe.test(value);
                    }
                  }
                  return false;
                }
                """
            )
        )

    def _expand_details(self, page) -> None:
        for name in [r"Show more", r"Daha fazla göster"]:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=3_000)
                page.wait_for_timeout(1_000)
                return
            except Exception:
                continue

    def _scroll_upload_dialog(self, page, delta_y: int) -> None:
        try:
            page.mouse.wheel(0, delta_y)
            page.wait_for_timeout(1_000)
        except Exception:
            pass

    def _click_related_video_select(self, page) -> bool:
        clicked = page.evaluate(
            """
            () => {
              const direct = document.querySelector('#linked-video-editor-link');
              if (direct) {
                direct.scrollIntoView({block: 'center', inline: 'center'});
                direct.click();
                return true;
              }

              const labelRe = /(Related video|İlgili video)/i;
              const actionRe = /^(Select|Seç|Choose|Add|Ekle|Edit|Düzenle)$/i;
              const roots = [...document.querySelectorAll('*')]
                .filter((el) => labelRe.test(el.textContent || ''));

              for (const root of roots) {
                let node = root;
                for (let depth = 0; node && depth < 9; depth += 1, node = node.parentElement) {
                  const buttons = [...node.querySelectorAll('button, ytcp-button, ytcp-icon-button, [role="button"]')];
                  const button = buttons.find((candidate) => {
                    const text = (candidate.innerText || candidate.textContent || candidate.getAttribute('aria-label') || '').trim();
                    const disabled = candidate.disabled || candidate.getAttribute('aria-disabled') === 'true';
                    return actionRe.test(text) && !disabled;
                  });
                  if (button) {
                    button.click();
                    return true;
                  }
                  const iconButton = buttons.find((candidate) => {
                    const disabled = candidate.disabled || candidate.getAttribute('aria-disabled') === 'true';
                    const iconText = (candidate.getAttribute('icon') || candidate.innerHTML || '').toLowerCase();
                    return !disabled && /(edit|pencil)/i.test(iconText);
                  });
                  if (iconButton) {
                    iconButton.click();
                    return true;
                  }
                }
              }
              return false;
            }
            """
        )
        return bool(clicked)

    def _search_and_choose_related_video(self, page, video_id: str, video_title: str) -> None:
        queries = [video_id, f"https://youtu.be/{video_id}", video_title]
        search_selectors = [
            "input[type='text']",
            "ytcp-searchbox input",
            "#search-input input",
            "[aria-label*='Search']",
            "[aria-label*='Ara']",
        ]

        for query in queries:
            if not query:
                continue
            for selector in search_selectors:
                locator = page.locator(selector).first
                try:
                    if locator.count():
                        locator.click(timeout=5_000)
                        locator.press("Meta+A")
                        locator.fill(query[:100])
                        locator.press("Enter")
                        page.wait_for_timeout(2_500)
                        if self._click_first_related_candidate(page):
                            return
                except Exception:
                    continue

        self._click_first_related_candidate(page)

    def _click_first_related_candidate(self, page) -> bool:
        selectors = [
            "ytcp-video-row",
            "ytcp-video-list-cell",
            "tp-yt-paper-item",
            "[role='option']",
            "[role='row']",
        ]
        for selector in selectors:
            locator = page.locator(selector)
            try:
                if locator.count():
                    locator.first.click(timeout=5_000)
                    page.wait_for_timeout(1_000)
                    return True
            except Exception:
                continue
        return False

    def _save_related_video(self, page) -> None:
        for name in [r"^Save$", r"^Kaydet$", r"^Done$", r"^Bitti$", r"^Apply$", r"^Uygula$", r"^Select$", r"^Seç$"]:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=5_000)
                page.wait_for_timeout(1_500)
                return
            except PlaywrightTimeoutError:
                continue

    def _save_video_edit(self, page) -> None:
        for name in [r"^Save$", r"^Kaydet$", r"Done", r"Bitti"]:
            try:
                button = page.get_by_role("button", name=re.compile(name, re.I)).first
                button.click(timeout=20_000)
                page.wait_for_timeout(2_000)
                return
            except PlaywrightTimeoutError:
                continue

    def _advance_to_visibility(self, page, add_end_screen: bool) -> None:
        self._click_next(page)
        if add_end_screen:
            logger.info("End screen is added after publish from the Studio details page.")
        self._click_next(page)
        self._click_next(page)

    def _click_next(self, page) -> None:
        self._click_named_button(
            page,
            [r"Next", r"İleri", r"Sonraki", r"Devam"],
            timeout=900_000,
        )

    def _try_add_end_screen(self, page) -> None:
        logger.info("Trying to add YouTube end screen...")
        try:
            page.get_by_text(re.compile(r"(End screen|Bitiş ekranı)", re.I)).first.wait_for(timeout=30_000)
            if not self._click_end_screen_add(page):
                logger.warning("End screen add button was not found; skipping.")
                return

            page.wait_for_timeout(2_000)
            self._choose_end_screen_template(page)
            self._save_end_screen(page)
            logger.info("End screen step completed.")
        except Exception as exc:
            logger.warning("End screen step skipped: %s", exc)
            self._dismiss_open_dialog(page)

    def _add_end_screen_from_editor(self, page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
            self._start_editor_if_needed(page)
            self._click_editor_end_screen_entry(page)
            page.wait_for_timeout(2_000)
            self._choose_end_screen_template(page)
            self._save_end_screen(page)
            self._save_video_edit(page)
            self._verify_end_screen_present(page)
            logger.info("End screen saved from Studio editor.")
        except Exception as exc:
            screenshot = "/private/tmp/youtube_studio_end_screen_failed.png"
            try:
                page.screenshot(path=screenshot, full_page=True)
            except Exception:
                pass
            raise TimeoutError(f"Could not add end screen. Screenshot: {screenshot}") from exc

    def _add_end_screen_from_details_page(self, page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=60_000)
            page.get_by_text(re.compile(r"(End screen|Bitiş ekranı)", re.I)).first.wait_for(
                timeout=90_000
            )
            self._scroll_to_end_screen(page)
            if not self._click_end_screen_edit(page):
                screenshot = "/private/tmp/youtube_studio_end_screen_button_failed.png"
                page.screenshot(path=screenshot, full_page=True)
                raise TimeoutError(f"End screen edit button not found. Screenshot: {screenshot}")

            page.wait_for_timeout(2_000)
            already_configured = self._end_screen_has_video_and_subscribe(page)
            if not already_configured:
                self._click_end_screen_template_candidate(page)
                page.wait_for_timeout(2_000)
            else:
                self._dismiss_open_dialog(page)
                logger.info("End screen already has video and subscribe elements.")
                return
            self._save_end_screen(page)
            if not self._end_screen_has_video_and_subscribe(page):
                raise TimeoutError("End screen did not contain a video and subscribe element.")
            self._save_video_edit(page)
            logger.info("End screen saved from Studio details page.")
        except Exception as exc:
            screenshot = "/private/tmp/youtube_studio_end_screen_failed.png"
            try:
                page.screenshot(path=screenshot, full_page=True)
            except Exception:
                pass
            raise TimeoutError(f"Could not add end screen. Screenshot: {screenshot}") from exc

    def _end_screen_has_video_and_subscribe(self, page) -> bool:
        try:
            text = page.locator("body").inner_text(timeout=3_000)
        except Exception:
            return False
        video_re = re.compile(r"(Video:|Video öğesi|Video element)", re.I)
        subscribe_re = re.compile(r"(Abone ol öğesi|Subscribe element|Subscribe:|Abone ol:)", re.I)
        playlist_missing_re = re.compile(r"(Lütfen oynatma listesi seçin|Please select a playlist)", re.I)
        return bool(video_re.search(text) and subscribe_re.search(text) and not playlist_missing_re.search(text))

    def _scroll_to_end_screen(self, page) -> None:
        page.evaluate(
            """
            () => {
              const labelRe = /(End screen|Bitiş ekranı)/i;
              const el = [...document.querySelectorAll('*')]
                .filter((node) => {
                  const text = (node.innerText || node.textContent || '').trim();
                  const box = node.getBoundingClientRect();
                  return text.length < 80 && box.width > 0 && box.height > 0 && labelRe.test(text);
                })
                .sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top)[0];
              if (el) el.scrollIntoView({block: 'center', inline: 'nearest'});
            }
            """
        )
        page.wait_for_timeout(1_000)

    def _click_end_screen_edit(self, page) -> bool:
        clicked = page.evaluate(
            """
            () => {
              const direct = document.querySelector('#endscreen-editor-link, #end-screen-editor-link');
              if (direct) {
                direct.scrollIntoView({block: 'center', inline: 'center'});
                direct.click();
                return true;
              }

              const labelRe = /(End screen|Bitiş ekranı)/i;
              const forbiddenRe = /(Subtitles|Altyazılar|Cards|Kartlar|Checks|Kontroller|Visibility|Görünürlük)/i;
              const labels = [...document.querySelectorAll('*')]
                .filter((el) => {
                  const text = (el.innerText || el.textContent || '').trim();
                  const box = el.getBoundingClientRect();
                  return text.length < 80 && box.width > 0 && box.height > 0 && labelRe.test(text);
                });

              for (const label of labels) {
                const labelBox = label.getBoundingClientRect();
                const controls = [...document.querySelectorAll(
                  'ytcp-icon-button, tp-yt-paper-icon-button, yt-icon-button, button, [role="button"]'
                )]
                  .map((button) => ({button, box: button.getBoundingClientRect()}))
                  .filter(({button, box}) => {
                    const text = (button.innerText || button.textContent || button.getAttribute('aria-label') || '').trim();
                    const disabled = button.disabled || button.getAttribute('aria-disabled') === 'true';
                    const html = (button.getAttribute('icon') || button.innerHTML || '').toLowerCase();
                    const centerY = box.top + (box.height / 2);
                    const nearLabel = centerY >= labelBox.top - 70 && centerY <= labelBox.bottom + 70;
                    const rightOfLabel = box.left > labelBox.left + 80;
                    const visible = box.width > 0 && box.height > 0;
                    const looksEditable = !text || /(Edit|Düzenle|Select|Seç|Choose|Add|Ekle)/i.test(text) || /(edit|pencil|create)/i.test(html);
                    return visible && !disabled && nearLabel && rightOfLabel && looksEditable;
                  })
                  .sort((a, b) => b.box.right - a.box.right);
                if (controls.length) {
                  controls[0].button.scrollIntoView({block: 'center', inline: 'center'});
                  controls[0].button.click();
                  return true;
                }

                for (let node = label; node && node !== document.body; node = node.parentElement) {
                  const box = node.getBoundingClientRect();
                  const text = (node.innerText || node.textContent || '').trim();
                  if (forbiddenRe.test(text.replace(labelRe, ''))) continue;
                  if (box.width >= 250 && box.height >= 45 && box.width <= 620 && box.height <= 140 && labelRe.test(text)) {
                    node.scrollIntoView({block: 'center', inline: 'center'});
                    node.click();
                    return true;
                  }
                }
              }
              return false;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(1_500)
        return bool(clicked)

    def _start_editor_if_needed(self, page) -> None:
        for name in [r"^Başla$", r"^Start$", r"^Get started$"]:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=10_000)
                page.wait_for_load_state("domcontentloaded", timeout=30_000)
                page.wait_for_timeout(3_000)
                return
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        for name in [r"^Başla$", r"^Start$", r"^Get started$"]:
            try:
                page.get_by_text(re.compile(name, re.I)).first.click(timeout=5_000)
                page.wait_for_timeout(3_000)
                return
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue

        clicked = page.evaluate(
            """
            () => {
              const walk = (root, out = []) => {
                for (const el of root.querySelectorAll('*')) {
                  out.push(el);
                  if (el.shadowRoot) walk(el.shadowRoot, out);
                }
                return out;
              };
              const startRe = /^(Başla|Start|Get started)$/i;
              const button = walk(document)
                .find((el) => startRe.test((el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim()));
              if (!button) return false;
              button.click();
              return true;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(3_000)
            return

        try:
            viewport = page.viewport_size or {"width": 1440, "height": 1000}
            page.mouse.click(viewport["width"] / 2, viewport["height"] - 90)
            page.wait_for_timeout(3_000)
        except Exception:
            pass

    def _click_editor_end_screen_entry(self, page) -> None:
        patterns = [
            re.compile(r"(End screen|Bitiş ekranı)", re.I),
            re.compile(r"(Add an end screen|Bitiş ekranı ekle)", re.I),
        ]
        for pattern in patterns:
            try:
                page.get_by_text(pattern).first.click(timeout=20_000)
                return
            except PlaywrightTimeoutError:
                continue

        clicked = page.evaluate(
            """
            () => {
              const labelRe = /(End screen|Bitiş ekranı)/i;
              const el = [...document.querySelectorAll('button, ytcp-button, [role="button"], a, div')]
                .find((node) => labelRe.test(node.innerText || node.textContent || ''));
              if (!el) return false;
              el.scrollIntoView({block: 'center', inline: 'center'});
              el.click();
              return true;
            }
            """
        )
        if not clicked:
            raise TimeoutError("End screen entry was not found in Studio editor.")

    def _verify_end_screen_present(self, page) -> None:
        page.wait_for_timeout(2_000)
        try:
            text = page.locator("body").inner_text(timeout=5_000)
        except Exception:
            text = ""
        present_re = re.compile(r"(End screen|Bitiş ekranı)", re.I)
        if present_re.search(text):
            return
        raise TimeoutError("End screen was not visible after saving.")

    def _click_end_screen_add(self, page) -> bool:
        clicked = page.evaluate(
            """
            () => {
              const labelRe = /(End screen|Bitiş ekranı)/i;
              const addRe = /^(Add|Ekle|Select|Seç|Choose|Şablon kullan|Use template)$/i;
              const roots = [...document.querySelectorAll('*')]
                .filter((el) => labelRe.test(el.textContent || ''));

              for (const root of roots) {
                let node = root;
                for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                  const buttons = [...node.querySelectorAll('button, ytcp-button, ytcp-icon-button, [role="button"]')];
                  const addButton = buttons.find((button) => {
                    const text = (button.innerText || button.textContent || button.getAttribute('aria-label') || '').trim();
                    const html = (button.getAttribute('icon') || button.innerHTML || '').toLowerCase();
                    const disabled = button.disabled || button.getAttribute('aria-disabled') === 'true';
                    return !disabled && (addRe.test(text) || /(add|plus)/i.test(html));
                  });
                  if (addButton) {
                    addButton.click();
                    return true;
                  }
                }
              }
              return false;
            }
            """
        )
        return bool(clicked)

    def _choose_end_screen_template(self, page) -> None:
        source_buttons = [
            r"Use template",
            r"Şablon kullan",
            r"Apply template",
            r"Şablonu uygula",
            r"Import from video",
            r"Videodan içe aktar",
            r"Import",
            r"İçe aktar",
        ]
        for name in source_buttons:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=5_000)
                page.wait_for_timeout(1_500)
                self._click_end_screen_template_candidate(page)
                return
            except PlaywrightTimeoutError:
                continue

        self._click_end_screen_template_candidate(page)

    def _click_end_screen_template_candidate(self, page) -> None:
        target = page.evaluate(
            """
            () => {
              const wanted = /(1\\s*video.*1\\s*subscribe|1\\s*video.*1\\s*abone)/i;
              const forbidden = /(playlist|oynatma)/i;
              const labels = [...document.querySelectorAll('*')]
                .filter((el) => {
                  const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
                  const box = el.getBoundingClientRect();
                  return box.width > 0 && box.height > 0
                    && text.length < 80
                    && wanted.test(text)
                    && !forbidden.test(text);
                })
                .sort((a, b) => {
                  const ab = a.getBoundingClientRect();
                  const bb = b.getBoundingClientRect();
                  return (ab.top - bb.top) || (ab.left - bb.left);
                });
              const label = labels[0];
              if (label) {
                let card = label;
                for (let node = label; node && node !== document.body; node = node.parentElement) {
                  const box = node.getBoundingClientRect();
                  const text = (node.innerText || node.textContent || '').replace(/\\s+/g, ' ').trim();
                  if (wanted.test(text) && !forbidden.test(text) && box.width >= 180 && box.height >= 100 && box.width <= 520 && box.height <= 260) {
                    card = node;
                  }
                }
                const box = card.getBoundingClientRect();
                card.scrollIntoView({block: 'center', inline: 'center'});
                const after = card.getBoundingClientRect();
                return {x: after.left + after.width / 2, y: after.top + after.height / 2};
              }

              const cards = [...document.querySelectorAll('ytve-template-card, tp-yt-paper-item, [role="option"], [role="row"], button, [role="button"], div')]
                .filter((el) => {
                  const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim();
                  const box = el.getBoundingClientRect();
                  return box.width > 0 && box.height > 0 && wanted.test(text) && !forbidden.test(text);
                })
                .sort((a, b) => {
                  const ab = a.getBoundingClientRect();
                  const bb = b.getBoundingClientRect();
                  return (ab.top - bb.top) || (ab.left - bb.left);
                });
              const card = cards[0];
              if (card) {
                card.scrollIntoView({block: 'center', inline: 'center'});
                const box = card.getBoundingClientRect();
                return {x: box.left + box.width / 2, y: box.top + box.height / 2};
              }
              const title = [...document.querySelectorAll('*')].find((el) => {
                const text = (el.innerText || el.textContent || '').trim();
                const box = el.getBoundingClientRect();
                return box.width > 0 && box.height > 0 && /(End Screens|Bitiş Ekranları)/i.test(text);
              });
              if (!title) return null;
              const dialog = title.closest('[role="dialog"]') || title.parentElement?.parentElement?.parentElement;
              if (!dialog) return null;
              const dbox = dialog.getBoundingClientRect();
              return {x: dbox.left + Math.min(270, dbox.width * 0.22), y: dbox.top + 230};
            }
            """
        )
        if target:
            page.mouse.click(target["x"], target["y"])
            page.wait_for_timeout(2_000)
            return
        raise TimeoutError("End screen template '1 video, 1 subscribe' was not found.")

    def _save_end_screen(self, page) -> None:
        save_buttons = [
            r"Save",
            r"Kaydet",
            r"Done",
            r"Bitti",
            r"Apply",
            r"Uygula",
            r"Import",
            r"İçe aktar",
        ]
        for _ in range(2):
            for name in save_buttons:
                try:
                    buttons = page.get_by_role("button", name=re.compile(name, re.I))
                    count = buttons.count()
                    for index in range(count):
                        button = buttons.nth(index)
                        try:
                            if button.is_disabled(timeout=1_000):
                                continue
                            button.click(timeout=5_000)
                            page.wait_for_timeout(1_500)
                            return
                        except Exception:
                            continue
                    if count:
                        continue
                    page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=5_000)
                    page.wait_for_timeout(1_500)
                    return
                except PlaywrightTimeoutError:
                    continue

    def _dismiss_open_dialog(self, page) -> None:
        for name in [r"^Cancel$", r"^İptal$", r"^Close$", r"^Kapat$"]:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=2_000)
                return
            except PlaywrightTimeoutError:
                continue
        try:
            page.keyboard.press("Escape")
        except Exception:
            pass

    def _set_public(self, page) -> None:
        patterns = [
            re.compile(r"^Public$", re.I),
            re.compile(r"^Herkese açık$", re.I),
        ]
        for pattern in patterns:
            try:
                page.get_by_text(pattern).click(timeout=30_000)
                return
            except PlaywrightTimeoutError:
                continue

        screenshot = "/private/tmp/youtube_studio_visibility_failed.png"
        page.screenshot(path=screenshot, full_page=True)
        raise TimeoutError(f"Could not select Public visibility. Screenshot: {screenshot}")

    def _publish(self, page) -> None:
        self._click_named_button(page, [r"Publish", r"Yayınla", r"Save", r"Kaydet"], timeout=900_000)

    def _click_named_button(self, page, names: list[str], timeout: int) -> None:
        role_timeout = min(timeout, 15_000)
        for name in names:
            try:
                page.get_by_role("button", name=re.compile(name, re.I)).first.click(timeout=role_timeout)
                return
            except PlaywrightTimeoutError:
                continue
            except Exception:
                continue
        if self._click_dialog_action_button(page, names):
            return
        raise TimeoutError(f"Could not click button matching: {names}")

    def _click_dialog_action_button(self, page, names: list[str]) -> bool:
        patterns = [name.strip("^$") for name in names]
        clicked = page.evaluate(
            """
            (patterns) => {
              const regexes = patterns.map((pattern) => new RegExp(pattern, 'i'));
              const controls = [...document.querySelectorAll('button, ytcp-button, [role="button"]')]
                .filter((el) => {
                  const text = (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim();
                  const disabled = el.disabled || el.getAttribute('aria-disabled') === 'true';
                  const box = el.getBoundingClientRect();
                  return !disabled && box.width > 0 && box.height > 0 && regexes.some((re) => re.test(text));
                })
                .map((el) => ({ el, box: el.getBoundingClientRect() }))
                .sort((a, b) => (b.box.bottom - a.box.bottom) || (b.box.right - a.box.right));

              if (!controls.length) return false;
              controls[0].el.click();
              return true;
            }
            """,
            patterns,
        )
        if clicked:
            page.wait_for_timeout(1_500)
        return bool(clicked)

    def _extract_video_id(self, page) -> str:
        page.wait_for_timeout(3_000)
        deadline_ms = self.timeout_ms
        pattern = re.compile(r"(?:youtu\.be/|watch\?v=|shorts/)([A-Za-z0-9_-]{6,})")
        try:
            page.wait_for_function(
                """() => [...document.querySelectorAll('a[href]')]
                  .some(a => /youtu\\.be\\/|watch\\?v=|shorts\\//.test(a.href))""",
                timeout=deadline_ms,
            )
        except PlaywrightTimeoutError:
            pass

        hrefs = page.locator("a[href]").evaluate_all("(els) => els.map((a) => a.href)")
        for href in hrefs:
            match = pattern.search(href)
            if match:
                return match.group(1)

        screenshot = "/private/tmp/youtube_studio_publish_no_id.png"
        page.screenshot(path=screenshot, full_page=True)
        raise TimeoutError(f"Upload may have finished, but video id was not found. Screenshot: {screenshot}")

    def _save_state(self, context) -> None:
        state_path = self.profile_dir / "storage_state.json"
        try:
            state_path.write_text(json.dumps(context.storage_state(), ensure_ascii=False, indent=2))
        except Exception as exc:
            logger.debug("Could not save YouTube Studio storage state: %s", exc)
