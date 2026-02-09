"""
Test Nano Banana for image-to-image renovation
"""
import asyncio
import os
import base64
from dotenv import load_dotenv
from google import genai

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

async def test():
    # First, get a test image from a property
    import sys
    sys.path.insert(0, '..')
    from src.scraper import RightmoveScraper
    scraper = RightmoveScraper()
    data = await scraper.scrape('https://www.rightmove.co.uk/properties/157872095')

    if not data.get('images'):
        print("No images found")
        return

    # Get first image
    first_key = list(data['images'].keys())[0]
    original_b64 = data['images'][first_key]['base64']
    original_bytes = base64.b64decode(original_b64)

    print(f"Testing Nano Banana with image: {first_key}")
    print(f"Original size: {len(original_bytes)} bytes")

    # Save original for comparison
    with open("test_original.jpg", "wb") as f:
        f.write(original_bytes)
    print("Saved original to test_original.jpg")

    # Test Nano Banana for image editing
    try:
        print("\nTrying Nano Banana Pro...")

        # Create the image part
        from google.genai import types

        response = client.models.generate_content(
            model="nano-banana-pro-preview",
            contents=[
                types.Part.from_bytes(data=original_bytes, mime_type="image/jpeg"),
                """Transform this room image into a beautifully renovated modern version.
Keep the EXACT same camera angle, room layout, and perspective.
Update the decor to be modern: fresh white walls, contemporary flooring,
updated fixtures, modern lighting. Make it look like a high-end renovation
while preserving the original room structure and viewpoint."""
            ]
        )

        print(f"Response type: {type(response)}")

        # Check for generated image
        if response.candidates:
            for part in response.candidates[0].content.parts:
                if hasattr(part, 'inline_data') and part.inline_data:
                    image_bytes = part.inline_data.data
                    with open("test_nano_banana_result.png", "wb") as f:
                        f.write(image_bytes)
                    print(f"✅ Generated image saved to test_nano_banana_result.png ({len(image_bytes)} bytes)")
                    return
                elif hasattr(part, 'text'):
                    print(f"Text response: {part.text[:200]}")

        print("❌ No image in response")

    except Exception as e:
        print(f"❌ Nano Banana error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test())
