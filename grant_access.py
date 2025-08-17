import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError

# Load .env if present (works both locally and on Heroku; on Heroku Config Vars override)
load_dotenv()

# ---------- Playwright / runtime config ----------
PLAYWRIGHT_HEADLESS = os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() == "true"
PLAYWRIGHT_NO_SANDBOX = os.getenv("PLAYWRIGHT_NO_SANDBOX", "1") == "1"

# Extra Chromium flags for containers/Heroku stability
CHROMIUM_ARGS = []
if PLAYWRIGHT_NO_SANDBOX:
    CHROMIUM_ARGS.extend([
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
    ])

DEFAULT_TIMEOUT = 10_000   # ms
LONG_TIMEOUT    = 12_000   # ms


# ---------- Utilities ----------
async def first_visible(page, selectors, timeout=DEFAULT_TIMEOUT):
    """
    Try selectors in order until one becomes visible; return its Locator.
    Raise PlaywrightTimeoutError if none match.
    """
    last_error = None
    for sel in selectors:
        loc = page.locator(sel).first
        try:
            await loc.wait_for(state="visible", timeout=timeout)
            # best-effort: also wait enabled briefly if possible
            try:
                await loc.wait_for(state="enabled", timeout=800)
            except Exception:
                pass
            return loc
        except PlaywrightTimeoutError as err:
            last_error = err
    raise PlaywrightTimeoutError(f"None of selectors {selectors} became visible") from last_error


async def find_and_click_exact_user_button(page, username):
    """Find an exact username result and click the Add/Grant access button in its row."""
    print(f"🔄 Looking for exact username '{username}' ...")
    await page.wait_for_timeout(3000)

    try:
        exact = f"text=@{username}" if not username.startswith("@") else f"text={username}"
        exact_el = page.locator(exact).first
        await exact_el.wait_for(state="visible", timeout=5000)
        print(f"✅ Found exact username '{username}'")

        # Button in same row/container
        user_row = exact_el.locator(
            "xpath=ancestor-or-self::*[self::tr or "
            "self::*[contains(@class, 'row') or contains(@class, 'user') or contains(@class, 'item')]][1]"
        )
        add_btn = user_row.locator(
            "button:has-text('Add access'), button:has-text('Grant access'), "
            "button[class*='add'], button[data-name*='add']"
        )

        if await add_btn.count() > 0:
            btn = add_btn.first
            await btn.wait_for(state="visible", timeout=3000)
            await btn.wait_for(state="enabled", timeout=3000)
            await btn.scroll_into_view_if_needed()
            await btn.click(force=True)
            print(f"✅ Clicked 'Add access' for {username}")
            return True

        # Fallback: first Add/Grant after the username element
        add_btn = exact_el.locator(
            "xpath=following::button[contains(., 'Add access') or contains(., 'Grant access')][1]"
        )
        if await add_btn.count() > 0:
            btn = add_btn.first
            await btn.wait_for(state="visible", timeout=3000)
            await btn.wait_for(state="enabled", timeout=3000)
            await btn.scroll_into_view_if_needed()
            await btn.click(force=True)
            print(f"✅ Clicked 'Add access' for {username} (fallback)")
            return True

        # Fallback: iterate visible usernames
        all_usernames = page.locator("text=/^@?[a-zA-Z0-9_]+$/")
        for i in range(await all_usernames.count()):
            el = all_usernames.nth(i)
            txt = (await el.text_content() or "").strip()
            if txt == username or txt == f"@{username}":
                user_row = el.locator(
                    "xpath=ancestor-or-self::*[self::tr or "
                    "self::*[contains(@class, 'row') or contains(@class, 'user') or contains(@class, 'item')]][1]"
                )
                add_btn = user_row.locator("button:has-text('Add access'), button:has-text('Grant access')")
                if await add_btn.count() > 0:
                    btn = add_btn.first
                    await btn.wait_for(state="visible", timeout=3000)
                    await btn.wait_for(state="enabled", timeout=3000)
                    await btn.scroll_into_view_if_needed()
                    await btn.click(force=True)
                    print(f"✅ Clicked 'Add access' for exact match {username} after iterating")
                    return True

        print(f"⚠️ Could not find 'Add access' near {username}")
        return False
    except Exception as e:
        print(f"⚠️ Could not find exact match for '{username}': {e}")
        return False


# ---------- Steps ----------
async def open_manage_access_dialog(page, username):
    try:
        print("🔍 Opening 'Manage access' dialog...")
        manage_btn = page.locator("button:has-text('Manage access')")
        await manage_btn.first.wait_for(state="visible", timeout=8000)
        await manage_btn.first.scroll_into_view_if_needed()
        await manage_btn.first.click()
    except PlaywrightTimeoutError as e:
        await page.screenshot(path=f"error_manage_btn_{username}.png")
        raise RuntimeError("Manage access button not found") from e


async def switch_to_add_new_users_tab(page, username):
    try:
        print("🔍 Switching to 'Add new users' tab...")
        add_tab = page.locator("[role='tab']:has-text('Add new users')")
        await add_tab.first.wait_for(state="visible", timeout=8000)
        await add_tab.first.scroll_into_view_if_needed()
        if (await add_tab.first.get_attribute("aria-selected")) != "true":
            await add_tab.first.click()
    except PlaywrightTimeoutError as e:
        await page.screenshot(path=f"error_add_tab_{username}.png")
        raise RuntimeError("'Add new users' tab not found") from e


async def search_and_add_user(page, username):
    try:
        print(f"🔍 Searching for username '{username}'...")
        search_input = await first_visible(
            page,
            [
                "input[placeholder*='grant them access']",
                "input[type='search']",
                "input[type='text']",
                "input[placeholder*='חפש משתמש']",
            ]
        )
        await search_input.fill(username)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2000)

        found = await find_and_click_exact_user_button(page, username)
        if not found:
            add_btn = await first_visible(page, ["text=Add access", "text=Grant access"])
            await add_btn.scroll_into_view_if_needed()
            await add_btn.click()
            print("✅ Clicked first available 'Add access' button")
    except PlaywrightTimeoutError as e:
        await page.screenshot(path=f"error_add_access_{username}.png")
        raise RuntimeError("Failed to add user access") from e


async def set_expiration_date(page, username):
    try:
        await page.mouse.wheel(0, 800)
        await page.wait_for_timeout(300)

        labels = ["No expiration date", "ללא תאריך תפוגה", "Без даты окончания", "Sin fecha de vencimiento"]
        checkbox_label = page.locator(",".join(f"label:has-text('{t}')" for t in labels))
        checkbox_input = checkbox_label.locator("input[type='checkbox']")

        try:
            await checkbox_input.wait_for(state="attached", timeout=4000)
            if await checkbox_input.is_checked():
                await checkbox_label.click()
                await page.wait_for_timeout(300)
        except PlaywrightTimeoutError:
            print("ℹ️ Checkbox not found – skipping toggle")

        expiry = (datetime.today() + timedelta(days=30)).strftime("%Y-%m-%d")
        date_input_selectors = ["input[placeholder='YYYY-MM-DD']", "input[placeholder='YYYY/MM/DD']", "input[type='date']"]
        try:
            date_input = await first_visible(page, date_input_selectors, timeout=5000)
            await date_input.fill(expiry)
            await date_input.press("Enter")
        except PlaywrightTimeoutError:
            print("ℹ️ Date input not found – keeping default expiration")

        # Close calendar/popover if open
        try:
            popover = page.locator("[role='dialog'], [class*='popover'], [class*='calendar']")
            try:
                await popover.wait_for(state="visible", timeout=1000)
                await page.mouse.click(10, 10)
            except PlaywrightTimeoutError:
                pass
        except Exception:
            pass
        await page.wait_for_timeout(500)

        # Apply / Confirm
        print("🟢 Trying to click Apply/Confirm button...")
        selectors = [
            "button[data-name='submit-button']:has-text('Apply')",
            "button:has-text('Apply')",
            "button[aria-label='Apply']",
            "button.primary:has-text('Apply')",
            "button[class*='apply']",
            "button[data-testid*='apply']",
            "button:has-text('Confirm')",
            "button:has-text('Save')",
            "button:has-text('OK')",
            "button[class*='primary'], button[class*='submit']",
        ]
        apply_btn = None
        for sel in selectors:
            btn = page.locator(sel).first
            try:
                await btn.wait_for(state="visible", timeout=3000)
                await btn.wait_for(state="enabled", timeout=3000)
                apply_btn = btn
                break
            except Exception:
                continue

        if not apply_btn:
            btns = page.locator("button, [role='button']")
            for i in range(await btns.count()):
                b = btns.nth(i)
                try:
                    txt = (await b.text_content() or "").lower()
                    if any(w in txt for w in ["apply", "confirm", "save", "ok"]):
                        await b.wait_for(state="visible", timeout=1200)
                        await b.wait_for(state="enabled", timeout=1200)
                        apply_btn = b
                        break
                except Exception:
                    continue

        if apply_btn:
            print(f"🔍 Found Apply-like button: '{await apply_btn.text_content()}'")
            await apply_btn.scroll_into_view_if_needed()
            await apply_btn.click(force=True)
            await page.wait_for_timeout(800)
        else:
            print("⚠️ No Apply found; clicking outside modal as fallback")
            await page.mouse.click(50, 50)
            await page.wait_for_timeout(500)

    except Exception as e:
        print(f"❌ Error in managing expiration: {e}")
        await page.screenshot(path=f"error_date_{username}.png")
        raise


async def click_grant_access(page, username):
    try:
        print("🔍 Looking for Grant access button...")
        await page.screenshot(path=f"debug_before_grant_{username}.png")

        grant_btn = await first_visible(
            page,
            [
                "button:has-text('Grant access')",
                "text=Grant access",
                "button:has-text('אישור גישה')",
                "text=אישור גישה",
                "button:has-text('Done')",
                "button:has-text('אישור')",
                "button:has-text('Confirm')",
                "button:has-text('OK')",
                "button:has-text('Submit')",
                "button:has-text('Post')",
                "button:has-text('Save')",
                "button:has-text('Apply')",
                "button[type='submit']",
                "button.primary",
                "button[data-testid*='grant']",
                "button[data-testid*='confirm']",
                "button[data-testid*='submit']",
                "button[class*='primary']",
                "button[class*='submit']",
                "button[class*='confirm']",
                "button[class*='grant']",
                "button[class*='btn-primary']",
                "button[class*='btn-success']",
                "button[class*='btn-confirm']",
            ],
            timeout=20_000,
        )

        print(f"🔍 Found button with text: '{await grant_btn.text_content()}'")
        await grant_btn.scroll_into_view_if_needed()
        try:
            await grant_btn.wait_for(state="enabled", timeout=8000)
        except PlaywrightTimeoutError:
            print("⚠️ Button not enabled; clicking anyway...")
        await grant_btn.click(force=True)
        await page.wait_for_timeout(2500)
        await page.screenshot(path=f"debug_after_grant_{username}.png")
    except PlaywrightTimeoutError as e:
        print(f"❌ Grant access button not found in time: {e}")
        await page.screenshot(path=f"error_grant_access_btn_{username}.png")
        # Debug: list buttons
        try:
            all_buttons = page.locator("button")
            print(f"🔍 Found {await all_buttons.count()} buttons on page")
            for i in range(await all_buttons.count()):
                b = all_buttons.nth(i)
                try:
                    t = await b.text_content()
                    vis = await b.is_visible()
                    en = await b.is_enabled()
                    print(f"  Button {i}: text='{t}', visible={vis}, enabled={en}")
                except Exception:
                    pass
        except Exception:
            pass
        # Try to close dialog
        try:
            close_btn = await first_visible(
                page,
                [
                    "button:has-text('Close')",
                    "button:has-text('Cancel')",
                    "button:has-text('Done')",
                    "button[aria-label*='close']",
                    "button[class*='close']",
                    "button[class*='cancel']",
                ],
                timeout=6000,
            )
            if close_btn:
                await close_btn.click()
                await page.wait_for_timeout(2000)
                print("✅ Closed dialog - maybe granted automatically")
        except Exception:
            pass
        raise
    except Exception as e:
        print(f"❌ General error clicking Grant access: {e}")
        await page.screenshot(path=f"error_final_{username}.png")
        raise


# ---------- Public API ----------
async def grant_access(username: str, script_url: str) -> bool:
    """
    Open the script page, add user, set expiration, and click Grant.
    Returns True on success.
    """
    print(f"🔐 Granting access to {username} on {script_url}")
    ok = True

    # Read env at runtime (so Celery/Heroku imports don't fail)
    session = os.getenv("TRADINGVIEW_SESSIONID")
    ecuid   = os.getenv("TRADINGVIEW_ECUID")
    if not session or not ecuid:
        raise RuntimeError("Missing TRADINGVIEW_SESSIONID / TRADINGVIEW_ECUID")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=PLAYWRIGHT_HEADLESS, args=CHROMIUM_ARGS)
        context = await browser.new_context()
        await context.add_cookies([
            {
                "name": "sessionid",
                "value": session,
                "domain": ".tradingview.com",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
            },
            {
                "name": "tv_ecuid",
                "value": ecuid,
                "domain": ".tradingview.com",
                "path": "/",
                "httpOnly": False,
                "secure": True,
                "sameSite": "Lax",
            },
        ])

        page = await context.new_page()
        # Global defaults for this page
        page.set_default_timeout(15_000)
        page.set_default_navigation_timeout(20_000)

        await page.goto(script_url)
        await page.wait_for_load_state("networkidle")

        try:
            await open_manage_access_dialog(page, username)
            await switch_to_add_new_users_tab(page, username)
            await search_and_add_user(page, username)
            await set_expiration_date(page, username)
            await click_grant_access(page, username)
        except Exception as e:
            print(f"❌ Error during grant_access process: {e}")
            ok = False
        finally:
            await context.close()
            await browser.close()

    print(f"✅ Done (success={ok})")
    return ok
