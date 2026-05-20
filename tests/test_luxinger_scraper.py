import os

from playwright.sync_api import Playwright, TimeoutError, sync_playwright


TARGET_URL = "https://www.lixinger.com/analytics/company/detail/hk/00700/700/fundamental/valuation/primary"


def _raise_if_blocked(page) -> None:
    body_text = page.locator("body").inner_text(timeout=5000).strip().lower()
    if "you are robot" in body_text:
        raise RuntimeError(
            "Lixinger blocked the automated browser with its anti-bot page before login. "
            "This recorder output cannot succeed until the site allows the session."
        )


def run(playwright: Playwright) -> None:
    username = os.getenv("LIXINGER_USERNAME", "roger249")
    password = os.getenv("LIXINGER_PASSWORD")
    if not password:
        raise ValueError("LIXINGER_PASSWORD environment variable not set")

    browser = playwright.webkit.launch(headless=False)
    context = browser.new_context()
    page = context.new_page()

    try:
        page.goto(TARGET_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        _raise_if_blocked(page)

        page.get_by_role("textbox", name="账号或手机号").fill(username)
        page.get_by_role("textbox", name="密码").fill(password)
        page.get_by_role("button", name="登录").click()
        page.wait_for_timeout(3000)
        _raise_if_blocked(page)

        page.get_by_text("PE-TTM", exact=False).click(timeout=5000)
        page.get_by_text("PB", exact=False).click(timeout=5000)
        page.get_by_text("PS-TTM", exact=False).click(timeout=5000)
    except TimeoutError as exc:
        raise RuntimeError(
            "The recorded selector flow no longer matches the live page. "
            "Inspect the current DOM and update the selectors before using this script."
        ) from exc
    finally:
        context.close()
        browser.close()


if __name__ == "__main__":
    with sync_playwright() as playwright:
        run(playwright)
