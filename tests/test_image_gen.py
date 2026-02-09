"""
Quick test for image generation
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_imagen():
    from google import genai

    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    print("Testing Imagen 4...")

    try:
        response = client.models.generate_images(
            model="imagen-4.0-generate-001",
            prompt="Professional interior design photograph of a beautifully renovated modern kitchen with white shaker cabinets, marble countertops, brass fixtures, and herringbone wood flooring. Natural daylight, architectural digest style.",
            config={
                "number_of_images": 1,
                "aspect_ratio": "4:3",
            }
        )

        if response.generated_images:
            print(f"✅ Image generated! Size: {len(response.generated_images[0].image.image_bytes)} bytes")

            # Save to file for inspection
            with open("test_generated_kitchen.png", "wb") as f:
                f.write(response.generated_images[0].image.image_bytes)
            print("✅ Saved to test_generated_kitchen.png")
        else:
            print("❌ No images in response")

    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_imagen())
