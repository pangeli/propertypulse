"""
Property analyzer using Gemini 3 Vision
"""
import os
import json
import base64
from typing import Optional
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))


class PropertyAnalyzer:
    """Analyzes property images using Gemini 3 Vision."""

    def __init__(self):
        # Using Gemini 3 Flash Preview for vision analysis (hackathon - Gemini 3 family)
        self.model = genai.GenerativeModel(
            "gemini-3-flash-preview",
            safety_settings={
                "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
                "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
                "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
                "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE",
            }
        )

        self.room_analysis_prompt = """Analyze this room image for renovation planning.

First, share your reasoning as you examine the image - describe what you see, your observations about condition, style, and age. Think out loud about issues and what work might be needed.

Then output JSON in this exact format:
```json
{
  "room_type": "kitchen|bathroom|bedroom|living_room|dining_room|hallway|study|utility|garden|exterior|other",
  "condition_score": <1-10, 1=derelict, 5=dated, 10=modern>,
  "estimated_age": "<decade, e.g. 1990s>",
  "issues": ["<issue 1>", "<issue 2>", "<issue 3>"],
  "renovation_items": [
    {"item": "<work needed>", "priority": "essential|recommended|optional", "scope": "repair|replace|upgrade"}
  ],
  "natural_light": "poor|adequate|good|excellent",
  "structural_concerns": "<concerns or None>"
}
```
Keep reasoning to 2-3 sentences. Max 5 issues, max 5 renovation items."""

        self.floorplan_prompt = """Analyze this floor plan image and extract room dimensions and layout information.

Return your analysis as JSON:
{
    "total_sqm": <estimated total square meters>,
    "total_sqft": <estimated total square feet>,
    "rooms": [
        {
            "name": "<room name as shown>",
            "dimensions_m": "<length x width in meters if shown>",
            "sqm": <estimated square meters>,
            "notes": "<any relevant notes about the room>"
        }
    ],
    "layout_notes": "<general notes about the layout, flow, potential improvements>",
    "renovation_opportunities": [
        "<potential layout improvement 1>",
        "<potential layout improvement 2>"
    ]
}

Extract all readable dimensions. If dimensions aren't clearly marked, estimate based on typical UK room sizes and proportions shown."""

    async def analyze_property(self, property_data: dict) -> dict:
        """
        Analyze all property images and return comprehensive assessment.

        Args:
            property_data: Dict containing images and property details

        Returns:
            Dict mapping room identifiers to analysis results
        """
        import asyncio
        results = {}

        # Analyze each room image
        images = property_data.get("images", {})
        for i, (room_key, image_data) in enumerate(images.items()):
            try:
                # Add small delay between requests to avoid rate limiting
                if i > 0:
                    await asyncio.sleep(1)

                print(f"  Analyzing {room_key}...")
                analysis = await self._analyze_room_image(
                    image_data.get("base64"),
                    image_data.get("label", room_key)
                )
                if analysis:
                    results[room_key] = analysis
            except Exception as e:
                print(f"Error analyzing {room_key}: {e}")
                results[room_key] = {"error": str(e)}

        # Analyze floorplan if available
        floorplan = property_data.get("floorplan")
        if floorplan and floorplan.get("base64"):
            try:
                results["floorplan_analysis"] = await self._analyze_floorplan(
                    floorplan.get("base64")
                )
            except Exception as e:
                print(f"Error analyzing floorplan: {e}")

        # Generate overall property assessment
        results["overall_assessment"] = self._generate_overall_assessment(
            results, property_data
        )

        return results

    async def _analyze_room_image(self, image_base64: str, room_label: str, retry_count: int = 0) -> Optional[dict]:
        """Analyze a single room image with Gemini Vision.

        Returns dict with 'reasoning' (AI's thought process) and analysis fields.
        """
        if not image_base64:
            return None

        import asyncio

        try:
            # Decode base64 to bytes
            image_bytes = base64.b64decode(image_base64)

            # Create image part for Gemini
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }

            # Call Gemini
            response = self.model.generate_content(
                [
                    f"Room label from listing: {room_label}\n\n{self.room_analysis_prompt}",
                    image_part
                ],
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 2048,
                }
            )

            # Parse response - extract reasoning AND JSON separately
            full_response = response.text
            reasoning_text = ""
            json_text = full_response

            # Extract reasoning (text before JSON block)
            if "```json" in full_response:
                parts = full_response.split("```json")
                reasoning_text = parts[0].strip()
                json_text = parts[1].split("```")[0]
            elif "```" in full_response:
                parts = full_response.split("```")
                reasoning_text = parts[0].strip()
                json_text = parts[1].split("```")[0] if len(parts) > 1 else parts[0]

            # Clean up JSON
            json_text = json_text.strip()

            # Try to find JSON object in response
            import re
            json_match = re.search(r'\{[\s\S]*\}', json_text)
            if json_match:
                json_text = json_match.group(0)

            result = json.loads(json_text)

            # Add the reasoning text to the result
            result["reasoning"] = reasoning_text

            return result

        except json.JSONDecodeError as e:
            # Retry once on JSON parse error
            if retry_count < 1:
                print(f"JSON parse error for {room_label}, retrying...")
                await asyncio.sleep(1)
                return await self._analyze_room_image(image_base64, room_label, retry_count + 1)
            print(f"JSON parse error for {room_label}: {e}")
            return {"error": "Failed to parse analysis", "raw": response_text[:500]}
        except Exception as e:
            error_msg = str(e)
            # Handle rate limiting with exponential backoff
            if "429" in error_msg and retry_count < 3:
                wait_time = (2 ** retry_count) * 2  # 2, 4, 8 seconds
                print(f"Rate limited on {room_label}, waiting {wait_time}s (retry {retry_count + 1}/3)")
                await asyncio.sleep(wait_time)
                return await self._analyze_room_image(image_base64, room_label, retry_count + 1)
            print(f"Analysis error for {room_label}: {e}")
            return {"error": str(e)}

    async def _analyze_floorplan(self, image_base64: str) -> Optional[dict]:
        """Analyze floorplan image to extract dimensions."""
        if not image_base64:
            return None

        try:
            image_bytes = base64.b64decode(image_base64)

            image_part = {
                "mime_type": "image/jpeg",
                "data": image_bytes
            }

            response = self.model.generate_content(
                [self.floorplan_prompt, image_part],
                generation_config={
                    "temperature": 0.2,
                    "max_output_tokens": 2048,
                }
            )

            response_text = response.text

            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]

            return json.loads(response_text.strip())

        except Exception as e:
            print(f"Floorplan analysis error: {e}")
            return {"error": str(e)}

    def _generate_overall_assessment(self, room_analyses: dict, property_data: dict) -> dict:
        """Generate overall property assessment from individual room analyses."""

        # Collect all condition scores
        condition_scores = []
        all_issues = []
        all_renovation_items = []

        for room_key, analysis in room_analyses.items():
            if isinstance(analysis, dict) and "condition_score" in analysis:
                condition_scores.append(analysis["condition_score"])
                all_issues.extend(analysis.get("issues", []))
                all_renovation_items.extend(analysis.get("renovation_items", []))

        # Calculate averages
        avg_condition = sum(condition_scores) / len(condition_scores) if condition_scores else 5

        # Categorize renovation items by priority
        essential_items = [i for i in all_renovation_items if i.get("priority") == "essential"]
        recommended_items = [i for i in all_renovation_items if i.get("priority") == "recommended"]
        optional_items = [i for i in all_renovation_items if i.get("priority") == "optional"]

        # Determine overall renovation scope
        if avg_condition <= 3:
            scope = "major_renovation"
            scope_description = "Property requires major renovation work"
        elif avg_condition <= 5:
            scope = "moderate_renovation"
            scope_description = "Property needs moderate updating throughout"
        elif avg_condition <= 7:
            scope = "light_refresh"
            scope_description = "Property would benefit from cosmetic updates"
        else:
            scope = "move_in_ready"
            scope_description = "Property is in good condition with minimal work needed"

        return {
            "average_condition": round(avg_condition, 1),
            "renovation_scope": scope,
            "scope_description": scope_description,
            "rooms_analyzed": len(condition_scores),
            "total_issues_found": len(all_issues),
            "essential_works": len(essential_items),
            "recommended_works": len(recommended_items),
            "optional_works": len(optional_items),
            "top_issues": all_issues[:10],  # Top 10 issues
            "property_type": property_data.get("property_type", "Unknown"),
            "listed_sqft": property_data.get("sqft", 0),
        }
