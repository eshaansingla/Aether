import asyncio
from pathlib import Path
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from app.config import BROWSER_PROFILE

class ChatGPTBrowser:
    """Visible persistent browser session. User signs in manually; credentials are never handled."""

    def __init__(self):
        self.playwright = None
        self.context = None
        self.page = None
        self.lock = asyncio.Lock()

    async def _ensure_browser(self):
        if self.context and self.page and not self.page.is_closed():
            return
        self.playwright = await async_playwright().start()
        BROWSER_PROFILE.mkdir(parents=True, exist_ok=True)
        self.context = await self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE),
            headless=False,
            viewport={"width": 1440, "height": 950},
            args=["--start-maximized"],
        )
        self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()

    async def submit_chatgpt_prompt(self, prompt: str, progress=None) -> str:
        async with self.lock:
            await self._ensure_browser()
            if progress:
                await progress("Opening ChatGPT in the visible browser.")
            await self.page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            await self.page.wait_for_timeout(1800)

            # Best-effort selectors; ChatGPT's UI can change. User can complete sign-in manually.
            composer = self.page.locator(
                '#prompt-textarea, [data-testid="prompt-textarea"], '
                'textarea[placeholder], div[contenteditable="true"]'
            ).first

            try:
                await composer.wait_for(state="visible", timeout=12000)
            except PlaywrightTimeoutError:
                if progress:
                    await progress("ChatGPT needs attention. Sign in manually in the browser, then retry.")
                raise RuntimeError(
                    "ChatGPT's message box was not found. Sign in manually if prompted, "
                    "then retry. If the interface changed, update selectors in tools/browser.py."
                )

            if progress:
                await progress("Submitting the optimized prompt to ChatGPT.")
            await composer.click()
            try:
                await composer.fill(prompt)
            except Exception:
                await self.page.keyboard.insert_text(prompt)

            send = self.page.locator(
                'button[data-testid="send-button"], button[aria-label*="Send"], '
                'button[aria-label*="send"]'
            ).last

            try:
                await send.wait_for(state="visible", timeout=8000)
                await send.click()
            except PlaywrightTimeoutError:
                await self.page.keyboard.press("Enter")

            if progress:
                await progress("Waiting for ChatGPT to finish generating the response.")
            await self.page.wait_for_timeout(1500)

            # Wait for generation to finish when a stop button is exposed.
            stop = self.page.locator(
                'button[data-testid="stop-button"], button[aria-label*="Stop"]'
            ).first
            try:
                await stop.wait_for(state="visible", timeout=12000)
                await stop.wait_for(state="hidden", timeout=180000)
            except PlaywrightTimeoutError:
                # Some UI versions do not expose the expected stop selector.
                await self.page.wait_for_timeout(20000)

            articles = self.page.locator('article[data-testid^="conversation-turn"], article')
            count = await articles.count()
            if count:
                response = (await articles.nth(count - 1).inner_text()).strip()
                if response:
                    return response

            # Fallback: collect visible assistant message containers.
            candidates = self.page.locator('[data-message-author-role="assistant"]')
            count = await candidates.count()
            if count:
                response = (await candidates.nth(count - 1).inner_text()).strip()
                if response:
                    return response

            raise RuntimeError("Could not extract the ChatGPT response. The page may have changed.")

    async def close(self):
        if self.context:
            await self.context.close()
            self.context = None
            self.page = None
        if self.playwright:
            await self.playwright.stop()
            self.playwright = None

browser = ChatGPTBrowser()
