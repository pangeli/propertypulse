"""Debug image extraction for a specific listing"""
import asyncio
from playwright.async_api import async_playwright

URL = "https://www.rightmove.co.uk/properties/157872095"

async def debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Try to click cookie banner
        try:
            btn = await page.query_selector('button[id*="accept"]')
            if btn:
                await btn.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        print("=== ALL IMAGES ===")
        images = await page.query_selector_all('img')
        for i, img in enumerate(images[:25]):
            src = await img.get_attribute('src') or ""
            alt = await img.get_attribute('alt') or ""
            print(f"{i}: [{alt[:40]}] {src[:80]}")

        await context.close()
        await browser.close()

asyncio.run(debug())
