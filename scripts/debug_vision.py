"""
Debug Gemini Vision responses
"""
import asyncio
import os
import base64
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

async def test_vision():
    # Load a test image
    from scraper import RightmoveScraper

    print("Scraping property for test image...")
    scraper = RightmoveScraper()
    data = await scraper.scrape("https://www.rightmove.co.uk/properties/161515835")

    if not data or not data.get('images'):
        print("No images to test")
        return

    # Get first image
    first_key = list(data['images'].keys())[0]
    image_b64 = data['images'][first_key]['base64']
    image_bytes = base64.b64decode(image_b64)

    print(f"Testing with image: {first_key}")
    print(f"Image size: {len(image_bytes)} bytes")

    # Test with different models
    models_to_test = [
        "gemini-2.0-flash",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    ]

    prompt = """Describe this room photo briefly. What type of room is it?"""

    for model_name in models_to_test:
        print(f"\n--- Testing {model_name} ---")
        try:
            model = genai.GenerativeModel(model_name)

            response = model.generate_content(
                [
                    prompt,
                    {"mime_type": "image/jpeg", "data": image_bytes}
                ],
                generation_config={"temperature": 0.2, "max_output_tokens": 200},
                safety_settings={
                    "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                    "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                    "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                    "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
                }
            )

            # Check response
            print(f"Response candidates: {len(response.candidates) if response.candidates else 0}")

            if response.candidates:
                candidate = response.candidates[0]
                print(f"Finish reason: {candidate.finish_reason}")

                if candidate.safety_ratings:
                    print("Safety ratings:")
                    for rating in candidate.safety_ratings:
                        print(f"  {rating.category}: {rating.probability}")

                if candidate.content and candidate.content.parts:
                    print(f"✅ Response: {response.text[:200]}...")
                else:
                    print("❌ No content in response")
            else:
                print("❌ No candidates in response")
                if hasattr(response, 'prompt_feedback'):
                    print(f"Prompt feedback: {response.prompt_feedback}")

        except Exception as e:
            print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(test_vision())
