"""
Debug script to inspect Rightmove page structure
"""
import asyncio
from playwright.async_api import async_playwright

TEST_URL = "https://www.rightmove.co.uk/properties/161515835"


async def debug_page():
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            viewport={'width': 1920, 'height': 1080}
        )
        page = await context.new_page()

        await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)

        # Accept cookies
        try:
            btn = await page.query_selector('button[id*="accept"]')
            if btn:
                await btn.click()
                await page.wait_for_timeout(1000)
        except:
            pass

        # Wait for page to fully load
        await page.wait_for_timeout(2000)

        # Find all images
        print("=== ALL IMAGES ===")
        images = await page.query_selector_all('img')
        for i, img in enumerate(images[:20]):
            src = await img.get_attribute('src')
            alt = await img.get_attribute('alt')
            print(f"{i}: {alt[:50] if alt else 'No alt'} -> {src[:80] if src else 'No src'}...")

        # Look for gallery/carousel
        print("\n=== GALLERY ELEMENTS ===")
        gallery_selectors = [
            '[data-test="gallery"]',
            '[class*="gallery"]',
            '[class*="Gallery"]',
            '[class*="carousel"]',
            '[class*="Carousel"]',
            '[class*="media"]',
            '[class*="photo"]',
            '.swiper',
            '[data-testid*="gallery"]',
            '[data-testid*="photo"]',
        ]

        for selector in gallery_selectors:
            els = await page.query_selector_all(selector)
            if els:
                print(f"Found {len(els)} elements for: {selector}")

        # Look for specific Rightmove image containers
        print("\n=== RIGHTMOVE SPECIFIC ===")
        rm_selectors = [
            '._2TqQt_VzNjiMcmPxVty8Mn img',  # Gallery images
            '[data-test="gallery-image"] img',
            '.gallery-main img',
            '.property-image img',
            'picture source',
            'picture img',
        ]

        for selector in rm_selectors:
            els = await page.query_selector_all(selector)
            if els:
                print(f"Found {len(els)} elements for: {selector}")
                for el in els[:3]:
                    if 'img' in selector:
                        src = await el.get_attribute('src')
                    else:
                        src = await el.get_attribute('srcset')
                    print(f"  -> {src[:100] if src else 'No src'}...")

        # Get page title and key info
        print("\n=== PAGE INFO ===")
        title = await page.title()
        print(f"Title: {title}")

        # Look for property details
        print("\n=== PROPERTY DETAILS ===")
        detail_selectors = [
            '[data-test="beds-label"]',
            '[data-test="baths-label"]',
            '[data-test="property-price"]',
            '[class*="price"]',
            '[class*="bedroom"]',
        ]

        for selector in detail_selectors:
            el = await page.query_selector(selector)
            if el:
                text = await el.inner_text()
                print(f"{selector}: {text}")

        # Save HTML for inspection
        html = await page.content()
        with open('debug_page.html', 'w') as f:
            f.write(html)
        print("\n✅ Saved debug_page.html for inspection")

        await context.close()
        await browser.close()


if __name__ == "__main__":
    asyncio.run(debug_page())
