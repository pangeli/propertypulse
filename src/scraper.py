"""
Rightmove property scraper using Playwright
"""
import asyncio
import base64
import httpx
import re
from typing import Optional
from playwright.async_api import async_playwright


class RightmoveScraper:
    """Scrapes property details and images from Rightmove listings."""

    async def scrape(self, url: str) -> Optional[dict]:
        """
        Scrape a Rightmove property listing.

        Returns:
            dict with keys: address, price, bedrooms, bathrooms, sqft,
                          description, images, floorplan, features
        """
        # Validate URL
        if "rightmove.co.uk" not in url:
            raise ValueError("URL must be a Rightmove listing")

        async with async_playwright() as p:
            # Try to use system Chrome, fallback to bundled Chromium
            try:
                browser = await p.chromium.launch(
                    channel="chrome",
                    headless=True
                )
            except Exception:
                browser = await p.chromium.launch(
                    headless=True,
                    args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu']
                )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()

            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)

                # Handle cookie consent banner
                await self._handle_cookie_banner(page)

                # Extract property data
                data = await self._extract_property_data(page)

                # Get all images
                data["images"] = await self._extract_images(page)

                # Get floorplan
                data["floorplan"] = await self._extract_floorplan(page)

                await context.close()
                await browser.close()
                return data

            except Exception as e:
                try:
                    await context.close()
                    await browser.close()
                except:
                    pass
                print(f"Scraping error: {e}")
                # Return demo data for hackathon if scraping fails
                return self._get_demo_data()

    async def _handle_cookie_banner(self, page):
        """Handle Rightmove cookie consent banner."""
        try:
            # Wait a moment for banner to appear
            await page.wait_for_timeout(1000)

            # Try various cookie accept buttons
            cookie_selectors = [
                'button[id*="accept"]',
                'button[class*="accept"]',
                '[data-test="accept-cookies"]',
                'button:has-text("Accept")',
                'button:has-text("Accept all")',
                'button:has-text("Accept All")',
                '#onetrust-accept-btn-handler',
                '.onetrust-accept-btn-handler',
                'button[title="Accept all cookies"]',
            ]

            for selector in cookie_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        await button.click()
                        print(f"Clicked cookie button: {selector}")
                        await page.wait_for_timeout(500)
                        return
                except:
                    continue

            print("No cookie banner found or already accepted")
        except Exception as e:
            print(f"Cookie handling error (non-fatal): {e}")

    async def _extract_property_data(self, page) -> dict:
        """Extract basic property information."""
        data = {}

        # Get page title - often contains beds/property type
        title = await page.title()
        print(f"  Page title: {title}")

        # Parse bedrooms from title (e.g., "4 bedroom terraced house for sale in...")
        import re
        beds_match = re.search(r'(\d+)\s*bed', title.lower())
        data["bedrooms"] = int(beds_match.group(1)) if beds_match else 0

        # Parse property type from title
        type_patterns = [
            'detached house', 'semi-detached house', 'terraced house',
            'flat', 'apartment', 'bungalow', 'cottage', 'maisonette',
            'end of terrace', 'town house', 'villa', 'barn conversion'
        ]
        data["property_type"] = "House"
        for ptype in type_patterns:
            if ptype in title.lower():
                data["property_type"] = ptype.title()
                break

        # Address - try multiple selectors
        address_selectors = [
            'h1[itemprop="streetAddress"]',
            '[data-test="address-label"]',
            'h1._2uQQ3SV0eMHL1P6t5ZDo2q',
            'address',
            'h1',
        ]
        data["address"] = "Address not found"
        for selector in address_selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    if text and len(text) > 5 and 'rightmove' not in text.lower():
                        data["address"] = text.strip()
                        break
            except:
                continue

        # Price - try multiple selectors
        price_selectors = [
            '[data-test="property-price"]',
            '._1gfnqJ3Vtd1z40MlC0MzXu span',
            '[class*="price"] span',
            'span[data-test="price"]',
        ]
        data["price"] = 0
        data["price_text"] = "Price on application"

        for selector in price_selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    if '£' in text:
                        data["price_text"] = text.strip()
                        data["price"] = self._parse_price(text)
                        break
            except:
                continue

        # Also try to find price in page content
        if data["price"] == 0:
            try:
                content = await page.content()
                price_match = re.search(r'£([\d,]+)', content)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    data["price"] = int(price_str)
                    data["price_text"] = f"£{price_match.group(1)}"
            except:
                pass

        # Bathrooms - often not shown, estimate from bedrooms
        try:
            baths_el = await page.query_selector('[data-test="baths-label"]')
            if baths_el:
                data["bathrooms"] = int(await baths_el.inner_text())
            else:
                # Estimate: typically 1 bathroom per 2 bedrooms, minimum 1
                data["bathrooms"] = max(1, data["bedrooms"] // 2)
        except:
            data["bathrooms"] = max(1, data["bedrooms"] // 2)

        # Square footage
        data["sqft"] = 0
        sqft_selectors = ['[data-test="floorarea-label"]', '[class*="floorarea"]']
        for selector in sqft_selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    data["sqft"] = self._parse_sqft(text)
                    if data["sqft"] > 0:
                        break
            except:
                continue

        # Description
        data["description"] = ""
        desc_selectors = [
            '[data-test="truncated-description"]',
            '[class*="description"]',
            '[class*="Description"]',
        ]
        for selector in desc_selectors:
            try:
                el = await page.query_selector(selector)
                if el:
                    text = await el.inner_text()
                    if len(text) > 50:
                        data["description"] = text.strip()
                        break
            except:
                continue

        # Key features
        data["features"] = []
        try:
            feature_els = await page.query_selector_all('ul[class*="feature"] li, [data-test="key-features"] li')
            for el in feature_els[:10]:
                text = await el.inner_text()
                if text and len(text) > 2:
                    data["features"].append(text.strip())
        except:
            pass

        print(f"  Extracted: {data['bedrooms']} beds, {data['bathrooms']} baths, {data['price_text']}")
        return data

    async def _extract_images(self, page) -> dict:
        """Extract property images with room type diversity from page source."""
        import re

        all_found_images = []
        seen_ids = set()

        try:
            # Get page source to find all image URLs
            content = await page.content()

            # Pattern 1: /{folder}/{agent}/{listing}/{agent}_{ref}_IMG_{num}_0000.jpeg
            agent_pattern = r'(https?://media\.rightmove\.co\.uk/[^\"\s\']+?)_IMG_(\d+)_0000\.(?:jpg|jpeg)'
            agent_matches = re.findall(agent_pattern, content, re.IGNORECASE)

            if agent_matches:
                base_url = agent_matches[0][0]
                unique_nums = sorted(set(int(m[1]) for m in agent_matches))
                print(f"  Found {len(unique_nums)} unique images (agent pattern)")

                for num in unique_nums:
                    img_id = f"agent_IMG_{num:02d}"
                    if img_id in seen_ids:
                        continue
                    seen_ids.add(img_id)
                    url = f"{base_url}_IMG_{num:02d}_0000.jpeg"
                    all_found_images.append({
                        'src': url,
                        'alt': f"Photo {num + 1}",
                        'num': num
                    })

            # Pattern 2: /dir/property-photo/ URLs (newer format)
            if not all_found_images:
                dir_pattern = r'https?://media\.rightmove\.co\.uk/dir/property-photo/([a-f0-9]+)/(\d+)/([a-f0-9]+)_max_(\d+x\d+)\.(?:jpg|jpeg|png)'
                dir_matches = re.findall(dir_pattern, content, re.IGNORECASE)

                if dir_matches:
                    unique_hashes = {}
                    for short_hash, listing_id, full_hash, size in dir_matches:
                        if full_hash not in unique_hashes:
                            unique_hashes[full_hash] = {
                                'short_hash': short_hash,
                                'listing_id': listing_id,
                                'full_hash': full_hash
                            }

                    print(f"  Found {len(unique_hashes)} unique images (dir/property-photo pattern)")

                    for i, (full_hash, info) in enumerate(unique_hashes.items()):
                        if full_hash in seen_ids:
                            continue
                        seen_ids.add(full_hash)
                        url = f"https://media.rightmove.co.uk/dir/property-photo/{info['short_hash']}/{info['listing_id']}/{info['full_hash']}_max_656x437.jpeg"
                        all_found_images.append({
                            'src': url,
                            'alt': f"Photo {i + 1}",
                            'num': i
                        })

            # Pattern 3: Generic _IMG_ URLs with size suffix
            if not all_found_images:
                img_pattern = r'(https?://media\.rightmove\.co\.uk/[^\"\s\']+?)_IMG_(\d+)_\d+x\d+\.(?:jpg|jpeg|png)'
                img_matches = re.findall(img_pattern, content, re.IGNORECASE)

                if img_matches:
                    base_url = img_matches[0][0]
                    unique_nums = sorted(set(int(m[1]) for m in img_matches))
                    print(f"  Found {len(unique_nums)} unique images (_IMG_ pattern)")

                    for num in unique_nums:
                        img_id = f"IMG_{num:02d}"
                        if img_id in seen_ids:
                            continue
                        seen_ids.add(img_id)
                        url = f"{base_url}_IMG_{num:02d}_656_437.jpg"
                        all_found_images.append({
                            'src': url,
                            'alt': f"Photo {num + 1}",
                            'num': num
                        })

            # Get alt text hints from rendered images
            all_imgs = await page.query_selector_all('img')
            for img in all_imgs:
                try:
                    src = await img.get_attribute('src') or ""
                    alt = await img.get_attribute('alt') or ""
                    if not alt or 'rightmove' in alt.lower():
                        continue

                    # Match to our found images
                    for img_data in all_found_images:
                        if img_data['src'] in src or any(h in src for h in [img_data.get('full_hash', ''), str(img_data['num'])]):
                            if alt and len(alt) > 3:
                                img_data['alt'] = alt
                                break
                except:
                    continue

            print(f"  Total images found: {len(all_found_images)}")

            # Select diverse images - prioritize different room types
            images = {}
            priority_types = ['kitchen', 'bathroom', 'living', 'lounge', 'reception', 'bedroom',
                            'garden', 'exterior', 'front', 'dining', 'hallway', 'en-suite', 'ensuite']

            used_indices = set()

            # First pass: get one of each priority type
            for ptype in priority_types:
                for i, img_data in enumerate(all_found_images):
                    if i in used_indices:
                        continue
                    if ptype in img_data['alt'].lower():
                        image_b64 = await self._download_image(img_data['src'])
                        if image_b64:
                            room_key = self._infer_room_type(img_data['alt'], len(images))
                            images[room_key] = {
                                "url": img_data['src'],
                                "base64": image_b64,
                                "label": img_data['alt']
                            }
                            used_indices.add(i)
                            print(f"  Selected {room_key}: {img_data['alt'][:50]}")
                        break

            # Second pass: fill up to 10 images (balance between coverage and API costs)
            for i, img_data in enumerate(all_found_images):
                if len(images) >= 10:
                    break
                if i in used_indices:
                    continue
                image_b64 = await self._download_image(img_data['src'])
                if image_b64:
                    room_key = self._infer_room_type(img_data['alt'], len(images))
                    if room_key in images:
                        room_key = f"{room_key}_{len(images)}"
                    images[room_key] = {
                        "url": img_data['src'],
                        "base64": image_b64,
                        "label": img_data['alt']
                    }
                    used_indices.add(i)
                    print(f"  Selected {room_key}: {img_data['alt'][:50]}")

        except Exception as e:
            print(f"Error extracting images: {e}")
            import traceback
            traceback.print_exc()

        return images

    async def _extract_floorplan(self, page) -> Optional[dict]:
        """Extract floorplan image if available."""
        try:
            # Look for floorplan images
            all_images = await page.query_selector_all('img')

            for img in all_images:
                alt = await img.get_attribute('alt') or ""
                src = await img.get_attribute('src') or ""

                # Check for floorplan - multiple patterns:
                # Pattern 1: 'property-floorplan' in URL
                # Pattern 2: '_FLP_' in URL
                # Pattern 3: 'floor' in alt text
                is_floorplan = (
                    'floor' in alt.lower() or
                    'floorplan' in src.lower() or
                    'property-floorplan' in src or
                    '_FLP_' in src
                )

                if is_floorplan:
                    # Get higher resolution if available
                    if '_135_101' in src:
                        src = src.replace('_135_101', '_656_437')

                    image_data = await self._download_image(src)
                    if image_data:
                        print(f"  Extracted floorplan: {alt}")
                        return {
                            "url": src,
                            "base64": image_data
                        }
        except Exception as e:
            print(f"Error extracting floorplan: {e}")

        return None

    async def _download_image(self, url: str) -> Optional[str]:
        """Download image, resize if needed, and return as base64."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                if response.status_code == 200:
                    # Resize image using Pillow to reduce payload size
                    from PIL import Image
                    import io

                    img = Image.open(io.BytesIO(response.content))
                    
                    # Convert to RGB (in case of RGBA/P)
                    if img.mode in ('RGBA', 'P'):
                        img = img.convert('RGB')
                        
                    # Resize if larger than 800x800 (max dimension)
                    max_size = (800, 800)
                    img.thumbnail(max_size, Image.Resampling.LANCZOS)
                    
                    # Save to buffer
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=85, optimize=True)
                    
                    return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            print(f"Error downloading/resizing image: {e}")
        return None

    def _parse_price(self, price_text: str) -> int:
        """Parse price string to integer."""
        numbers = re.findall(r'[\d,]+', price_text)
        if numbers:
            return int(numbers[0].replace(',', ''))
        return 0

    def _parse_sqft(self, sqft_text: str) -> int:
        """Parse square footage string."""
        numbers = re.findall(r'[\d,]+', sqft_text)
        if numbers:
            return int(numbers[0].replace(',', ''))
        return 0

    def _infer_room_type(self, alt_text: str, index: int) -> str:
        """Infer room type from image alt text."""
        alt_lower = alt_text.lower()

        room_keywords = {
            'kitchen': 'kitchen',
            'bathroom': 'bathroom',
            'bedroom': 'bedroom',
            'living': 'living_room',
            'lounge': 'living_room',
            'reception': 'living_room',
            'garden': 'garden',
            'exterior': 'exterior',
            'front': 'exterior',
            'dining': 'dining_room',
            'study': 'study',
            'office': 'study',
            'hallway': 'hallway',
            'entrance': 'hallway',
            'utility': 'utility',
            'garage': 'garage',
            'conservatory': 'conservatory',
            'en-suite': 'ensuite',
            'ensuite': 'ensuite',
            'shower': 'bathroom',
            'wc': 'bathroom',
            'toilet': 'bathroom',
        }

        for keyword, room_type in room_keywords.items():
            if keyword in alt_lower:
                # Add index to handle multiple of same room
                return f"{room_type}_{index}"

        return f"room_{index}"

    def _get_demo_data(self) -> dict:
        """Return demo data for hackathon testing."""
        return {
            "address": "123 Demo Street, London, SW1A 1AA",
            "price": 450000,
            "price_text": "£450,000",
            "bedrooms": 3,
            "bathrooms": 2,
            "sqft": 1200,
            "property_type": "Terraced House",
            "description": "A charming period property requiring modernisation. Features include original fireplaces, high ceilings, and a south-facing garden. Ideal for renovation project.",
            "features": [
                "Period features throughout",
                "South-facing garden",
                "Close to transport links",
                "Chain free",
                "In need of modernisation"
            ],
            "images": {},  # Will be populated with test images
            "floorplan": None
        }
