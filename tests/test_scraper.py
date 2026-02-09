"""
Quick test script for the scraper and analyzer
"""
import asyncio
import json
import sys
sys.path.insert(0, '..')
from src.scraper import RightmoveScraper
from src.analyzer import PropertyAnalyzer
from src.cost_engine import CostEngine

TEST_URL = "https://www.rightmove.co.uk/properties/161515835"


async def test_scraper():
    print("=" * 60)
    print("Testing Rightmove Scraper")
    print("=" * 60)

    scraper = RightmoveScraper()
    data = await scraper.scrape(TEST_URL)

    if data:
        print(f"\n✅ Address: {data.get('address')}")
        print(f"✅ Price: {data.get('price_text')}")
        print(f"✅ Bedrooms: {data.get('bedrooms')}")
        print(f"✅ Bathrooms: {data.get('bathrooms')}")
        print(f"✅ Sqft: {data.get('sqft')}")
        print(f"✅ Property Type: {data.get('property_type')}")
        print(f"✅ Images found: {len(data.get('images', {}))}")
        print(f"✅ Has floorplan: {data.get('floorplan') is not None}")
        print(f"\nFeatures:")
        for f in data.get('features', [])[:5]:
            print(f"  - {f}")

        return data
    else:
        print("❌ Failed to scrape property")
        return None


async def test_analyzer(property_data: dict):
    print("\n" + "=" * 60)
    print("Testing Gemini Analyzer")
    print("=" * 60)

    if not property_data.get('images'):
        print("⚠️ No images to analyze - skipping")
        return None

    analyzer = PropertyAnalyzer()
    results = await analyzer.analyze_property(property_data)

    print(f"\n✅ Rooms analyzed: {len(results) - 2}")  # -2 for floorplan and overall

    # Show overall assessment
    overall = results.get('overall_assessment', {})
    print(f"\n📊 Overall Assessment:")
    print(f"   Average condition: {overall.get('average_condition')}/10")
    print(f"   Renovation scope: {overall.get('renovation_scope')}")
    print(f"   Total issues found: {overall.get('total_issues_found')}")

    # Show a sample room analysis
    for room_key, analysis in results.items():
        if room_key not in ['floorplan_analysis', 'overall_assessment'] and isinstance(analysis, dict) and 'condition_score' in analysis:
            print(f"\n🏠 Sample Room: {room_key}")
            print(f"   Type: {analysis.get('room_type')}")
            print(f"   Condition: {analysis.get('condition_score')}/10")
            print(f"   Age: {analysis.get('estimated_age')}")
            print(f"   Issues: {analysis.get('issues', [])[:3]}")
            break

    return results


def test_cost_engine(room_analyses: dict, property_data: dict):
    print("\n" + "=" * 60)
    print("Testing Cost Engine")
    print("=" * 60)

    engine = CostEngine()
    costs = engine.calculate(room_analyses, property_data)

    print(f"\n💷 Cost Breakdown:")
    print(f"   Budget: £{costs['grand_total']['low']:,}")
    print(f"   Mid-range: £{costs['grand_total']['mid']:,}")
    print(f"   Premium: £{costs['grand_total']['high']:,}")

    print(f"\n📂 By Category:")
    for cat, amounts in costs.get('by_category', {}).items():
        print(f"   {cat}: £{amounts['mid']:,}")

    return costs


async def test_image_gen(room_analyses: dict, property_data: dict):
    print("\n" + "=" * 60)
    print("Testing Image Generation (Imagen 4)")
    print("=" * 60)

    from image_gen import RenovationVisualizer

    visualizer = RenovationVisualizer()

    if not visualizer.imagen_available:
        print("⚠️ Imagen not available - skipping")
        return {}

    # Only test first room to save time/quota
    results = {}
    for room_key, analysis in list(room_analyses.items())[:1]:
        if room_key in ["floorplan_analysis", "overall_assessment"]:
            continue
        if not isinstance(analysis, dict) or "error" in analysis:
            continue

        room_type = analysis.get("room_type", "room")
        print(f"\n  Generating 'after' image for {room_key} ({room_type})...")

        try:
            # Generate description
            description = visualizer._create_renovation_prompt(room_type, analysis)
            print(f"  Description: {description[:100]}...")

            # Transform image using Nano Banana
            original_b64 = property_data['images'][room_key]['base64']
            image_b64 = await visualizer._transform_image(original_b64, description, room_type)
            if image_b64:
                print(f"  ✅ Image generated! ({len(image_b64)} chars base64)")

                # Save to file
                import base64
                with open(f"test_after_{room_key}.png", "wb") as f:
                    f.write(base64.b64decode(image_b64))
                print(f"  ✅ Saved to test_after_{room_key}.png")

                results[room_key] = {"image": image_b64, "description": description}
            else:
                print("  ❌ No image generated")
        except Exception as e:
            print(f"  ❌ Error: {e}")

    return results


async def main():
    print("\n🏠 PropertyPulse Test Suite\n")

    # Test 1: Scraping
    property_data = await test_scraper()

    if not property_data:
        print("\n❌ Scraping failed - cannot continue")
        return

    # Test 2: Gemini Analysis
    room_analyses = await test_analyzer(property_data)

    if not room_analyses:
        print("\n⚠️ Analysis skipped - using mock data for cost test")
        room_analyses = {
            "kitchen_0": {
                "room_type": "kitchen",
                "condition_score": 4,
                "issues": ["dated cabinets", "worn flooring"],
                "renovation_items": [
                    {"item": "Replace kitchen units", "priority": "recommended", "scope": "replace"}
                ]
            }
        }

    # Test 3: Cost Estimation
    test_cost_engine(room_analyses, property_data)

    # Test 4: Image Generation
    await test_image_gen(room_analyses, property_data)

    print("\n" + "=" * 60)
    print("✅ All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
