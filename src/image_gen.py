"""
Renovation visualization using Nano Banana Pro
Transforms original room images into renovated versions while preserving angle/layout
"""
import os
import base64
import asyncio
from typing import Dict, Optional
import google.generativeai as genai
from google import genai as genai_client
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# Configure APIs
api_key = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=api_key)


class RenovationVisualizer:
    """Generate renovation visualizations using Nano Banana Pro."""

    def __init__(self):
        # Gemini for generating renovation descriptions
        # Using Gemini 3 Flash Preview as per Hackathon requirements
        self.model = genai.GenerativeModel("gemini-3-flash-preview")

        # Nano Banana Pro for image-to-image transformation
        self.client = None
        self.imagen_available = False

        try:
            self.client = genai_client.Client(api_key=api_key)
            self.imagen_available = True
            print("Nano Banana Pro initialized successfully")
        except Exception as e:
            print(f"Nano Banana setup error: {e}")
            self.imagen_available = False

    async def generate_after_images(
        self,
        original_images: Dict[str, dict],
        room_analyses: Dict[str, dict]
    ) -> Dict[str, dict]:
        """
        Generate "after" renovation images from original room photos.
        Preserves camera angle, layout, and perspective.
        """
        results = {}

        for room_key, analysis in room_analyses.items():
            if room_key in ["floorplan_analysis", "overall_assessment"]:
                continue

            if not isinstance(analysis, dict) or "error" in analysis:
                continue

            room_type = analysis.get("room_type", "room")
            condition = analysis.get("condition_score", 5)

            # Only generate for rooms that need work
            if condition >= 8:
                continue

            # Get original image
            original = original_images.get(room_key, {})
            original_b64 = original.get("base64")

            if not original_b64:
                print(f"  No original image for {room_key}, skipping")
                continue

            try:
                # Detect architectural style from analysis
                style = self._detect_architectural_style(analysis)
                print(f"  Transforming {room_key} ({room_type}, style: {style})...")

                # Generate renovation description based on analysis and style
                reno_prompt = self._create_renovation_prompt(room_type, analysis)

                # Transform image using Nano Banana with style awareness
                generated_b64 = await self._transform_image(
                    original_b64,
                    reno_prompt,
                    room_type,
                    style
                )

                results[room_key] = {
                    "room_type": room_type,
                    "original_image": original_b64,  # Include original for slider
                    "generated_image": generated_b64,
                    "renovation_description": reno_prompt,
                    "original_condition": condition,
                }

                # Rate limiting
                await asyncio.sleep(2)

            except Exception as e:
                print(f"  Error transforming {room_key}: {e}")
                results[room_key] = {
                    "room_type": room_type,
                    "original_image": original_b64,
                    "generated_image": None,
                    "error": str(e),
                    "original_condition": condition,
                }

        return results

    def _detect_architectural_style(self, analysis: dict) -> str:
        """Detect architectural style from analysis."""
        age = analysis.get("estimated_age", "").lower()
        issues = " ".join(analysis.get("issues", [])).lower()
        all_text = f"{age} {issues}"

        # Check for period indicators
        if any(x in all_text for x in ["victorian", "1880", "1890", "1900", "edwardian", "1910"]):
            return "victorian"
        elif any(x in all_text for x in ["georgian", "1800", "1820", "1830", "1840", "regency"]):
            return "georgian"
        elif any(x in all_text for x in ["1920", "1930", "art deco", "inter-war"]):
            return "1930s"
        elif any(x in all_text for x in ["1950", "1960", "post-war", "post war"]):
            return "postwar"
        elif any(x in all_text for x in ["1970", "1980"]):
            return "1970s_80s"
        elif any(x in all_text for x in ["1990", "2000", "modern", "contemporary"]):
            return "modern"

        # Check for architectural features in issues
        if any(x in all_text for x in ["sash window", "bay window", "original feature", "period", "cornice", "ornate"]):
            return "victorian"
        elif any(x in all_text for x in ["pebbledash", "render", "roughcast"]):
            return "postwar"

        return "unknown"

    def _create_renovation_prompt(self, room_type: str, analysis: dict) -> str:
        """Create a specific renovation prompt based on room analysis and architectural style."""
        issues = analysis.get("issues", [])
        renovation_items = analysis.get("renovation_items", [])

        # Detect architectural style
        style = self._detect_architectural_style(analysis)

        # Build specific improvements based on issues
        improvements = []

        for item in renovation_items[:5]:
            item_text = item.get("item", "").lower()
            if "floor" in item_text:
                if style in ["victorian", "georgian"]:
                    improvements.append("restored original floorboards or period-appropriate flooring")
                else:
                    improvements.append("modern engineered oak flooring")
            elif "wall" in item_text or "paint" in item_text:
                if style in ["victorian", "georgian"]:
                    improvements.append("freshly painted walls in heritage colours")
                else:
                    improvements.append("fresh white walls with a modern matte finish")
            elif "kitchen" in item_text or "cabinet" in item_text:
                if style in ["victorian", "georgian"]:
                    improvements.append("classic shaker kitchen with traditional details")
                else:
                    improvements.append("sleek contemporary white kitchen cabinets")
            elif "bathroom" in item_text or "suite" in item_text:
                improvements.append("modern white bathroom suite with chrome fixtures")
            elif "window" in item_text:
                if style in ["victorian", "georgian"]:
                    improvements.append("restored or sympathetically replaced sash windows")
                else:
                    improvements.append("clean modern window treatments")
            elif "light" in item_text:
                improvements.append("appropriate period or contemporary lighting")
            elif "render" in item_text or "facade" in item_text:
                if style in ["victorian", "georgian"]:
                    improvements.append("cleaned and repointed original brickwork")
                else:
                    improvements.append("fresh smooth render")
            elif "door" in item_text:
                if style in ["victorian", "georgian"]:
                    improvements.append("restored or period-style front door")
                else:
                    improvements.append("contemporary composite front door")
            elif "roof" in item_text:
                improvements.append("clean slate or tile roof")

        if not improvements:
            # Default improvements based on room type AND architectural style
            if room_type == "kitchen":
                if style in ["victorian", "georgian"]:
                    improvements = ["classic shaker cabinets", "wooden worktops or stone", "period-appropriate flooring"]
                else:
                    improvements = ["modern white shaker cabinets", "quartz countertops", "herringbone floor"]
            elif room_type == "bathroom":
                improvements = ["modern white suite", "large format tiles", "chrome fixtures"]
            elif room_type == "bedroom":
                if style in ["victorian", "georgian"]:
                    improvements = ["freshly painted walls in soft heritage colours", "restored flooring", "period lighting"]
                else:
                    improvements = ["fresh neutral walls", "modern flooring", "contemporary lighting"]
            elif room_type == "living_room":
                if style in ["victorian", "georgian"]:
                    improvements = ["restored period features", "freshly painted in heritage colours", "appropriate flooring"]
                else:
                    improvements = ["fresh white walls", "engineered oak flooring", "modern fixtures"]
            elif room_type in ["exterior", "front", "facade"]:
                if style in ["victorian", "georgian"]:
                    improvements = ["cleaned and repointed brickwork", "restored sash windows", "period-appropriate front door", "tidy front garden"]
                elif style == "1930s":
                    improvements = ["fresh render or cleaned brickwork", "period-style windows", "art deco door details", "neat hedging"]
                else:
                    improvements = ["fresh painted or rendered facade", "modern composite front door", "clean windows", "tidy front garden"]
            elif room_type == "garden":
                improvements = ["manicured lawn", "patio area", "fresh fencing", "mature planting"]
            else:
                improvements = ["fresh decor", "updated flooring", "appropriate styling"]

        # Different return text for exterior vs interior, style-aware
        if room_type in ["exterior", "front", "facade", "garden"]:
            if style in ["victorian", "georgian"]:
                return f"Refresh the period exterior: {', '.join(improvements)}. Preserve Victorian/Georgian character, estate agent quality."
            elif style == "1930s":
                return f"Refresh the 1930s exterior: {', '.join(improvements)}. Preserve period character, estate agent quality."
            else:
                return f"Renovate with {', '.join(improvements)}. Modern kerb appeal, estate agent quality."

        if style in ["victorian", "georgian"]:
            return f"Transform into a beautifully renovated period {room_type} with {', '.join(improvements)}. Preserve character, bright, magazine-quality."
        return f"Transform into a beautifully renovated {room_type} with {', '.join(improvements)}. Modern, bright, magazine-quality interior."

    async def _transform_image(
        self,
        original_b64: str,
        renovation_prompt: str,
        room_type: str,
        style: str = "modern"
    ) -> Optional[str]:
        """Transform original image using Nano Banana Pro."""
        if not self.imagen_available or not self.client:
            return None

        try:
            # Decode original image
            original_bytes = base64.b64decode(original_b64)

            # Build prompt based on room type AND architectural style
            is_exterior = room_type in ["exterior", "garden", "front", "facade"]
            is_period = style in ["victorian", "georgian", "1930s"]

            if is_exterior:
                if is_period:
                    # Period property - preserve character
                    full_prompt = f"""Refresh ONLY the CENTER property in this image while PRESERVING its {style.upper()} architectural character.

CRITICAL RULES:
1. PIXEL-PERFECT ALIGNMENT: Do not crop, zoom, rotate, or shift the image. The output MUST overlap perfectly with the original.
2. ONLY refresh the MAIN/CENTER property - the one that is the focus of the listing
3. DO NOT change neighboring houses, adjacent facades, or other properties
4. Keep neighboring properties EXACTLY as they appear in the original
5. Preserve the EXACT camera angle, perspective, and composition
6. Do not alter the street, pavement, cars, or background elements
7. PRESERVE the architectural style - DO NOT modernize to white render or contemporary style
8. Keep original brickwork, stonework, or period render - just clean and restore it
9. Preserve period windows (sash windows, bay windows) - restore, don't replace with modern uPVC
10. Keep period features like decorative brickwork, cornices, original doors

For the CENTER property ONLY, apply these SYMPATHETIC improvements:
{renovation_prompt}

Style: Careful period restoration, not modernization. The property should look beautifully RESTORED, not converted to modern style.
Clean brickwork, restored windows, period-appropriate door, tidy garden. Estate agent quality photography."""
                else:
                    # Modern/post-war property - can modernize
                    full_prompt = f"""Transform ONLY the CENTER property in this image into a beautifully renovated version.

CRITICAL RULES:
1. PIXEL-PERFECT ALIGNMENT: Do not crop, zoom, rotate, or shift the image. The output MUST overlap perfectly with the original.
2. ONLY renovate the MAIN/CENTER property - the one that is the focus of the listing
3. DO NOT change neighboring houses, adjacent facades, or other properties in the image
4. Keep neighboring properties EXACTLY as they appear in the original
5. Preserve the EXACT camera angle, perspective, and composition
6. Do not alter the street, pavement, cars, or background elements

For the CENTER property ONLY, apply these changes:
{renovation_prompt}

Style: High-end UK property renovation, natural lighting, estate agent quality photography.
The result should look like only the target property has been renovated, with all surroundings unchanged."""
            else:
                # Interior rooms
                if is_period:
                    full_prompt = f"""Transform this {room_type} into a beautifully renovated space that PRESERVES period character.

CRITICAL RULES:
1. PIXEL-PERFECT ALIGNMENT: Do not crop, zoom, rotate, or shift the image. The output MUST overlap perfectly with the original.
2. Keep the EXACT same camera angle, room layout, window positions, and perspective.
3. Do NOT change the room shape or viewpoint.
4. PRESERVE period features like cornices, ceiling roses, fireplaces, sash windows, picture rails.

Renovation changes:
{renovation_prompt}

Style: Sympathetic period renovation, not over-modernization. Bright, magazine-quality but respecting original character."""
                else:
                    full_prompt = f"""Transform this {room_type} image into a beautifully renovated modern version.

CRITICAL RULES:
1. PIXEL-PERFECT ALIGNMENT: Do not crop, zoom, rotate, or shift the image. The output MUST overlap perfectly with the original.
2. Keep the EXACT same camera angle, room layout, window positions, and perspective.
3. Do NOT change the room shape or viewpoint.

Renovation changes:
{renovation_prompt}

Style: High-end UK home renovation, natural lighting, Architectural Digest quality.
Make it look professionally renovated while preserving the original room structure."""

            # Use Nano Banana Pro for image-to-image
            response = self.client.models.generate_content(
                model="nano-banana-pro-preview",
                contents=[
                    types.Part.from_bytes(data=original_bytes, mime_type="image/jpeg"),
                    full_prompt
                ]
            )

            # Extract generated image from response
            if response.candidates:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'inline_data') and part.inline_data:
                        raw_data = part.inline_data.data
                        mime_type = getattr(part.inline_data, 'mime_type', 'image/jpeg')

                        # Handle different data formats from Google API
                        if isinstance(raw_data, str):
                            # Already base64 encoded string - decode to bytes first
                            try:
                                image_bytes = base64.b64decode(raw_data)
                                print(f"    Decoded base64 string to {len(image_bytes)} bytes")
                            except Exception:
                                # Not valid base64, treat as raw string bytes
                                image_bytes = raw_data.encode('latin-1')
                        elif isinstance(raw_data, bytes):
                            # Check if bytes are actually base64-encoded text
                            # Base64 images typically start with specific patterns when decoded
                            # Raw JPEG starts with \xff\xd8, PNG with \x89PNG
                            if raw_data[:2] == b'\xff\xd8' or raw_data[:4] == b'\x89PNG':
                                # Already raw image bytes
                                image_bytes = raw_data
                                print(f"    Using raw image bytes directly")
                            else:
                                # Might be base64 bytes - try to decode
                                try:
                                    decoded = base64.b64decode(raw_data)
                                    if decoded[:2] == b'\xff\xd8' or decoded[:4] == b'\x89PNG':
                                        image_bytes = decoded
                                        print(f"    Decoded base64 bytes to {len(image_bytes)} bytes")
                                    else:
                                        # Not valid image after decode, use original
                                        image_bytes = raw_data
                                        print(f"    Using bytes as-is (unknown format)")
                                except Exception:
                                    # Not base64, use as-is
                                    image_bytes = raw_data
                                    print(f"    Using raw bytes (not base64)")
                        else:
                            # Unknown type
                            image_bytes = bytes(raw_data) if raw_data else b''
                            print(f"    Converted unknown type to bytes")

                        print(f"    Raw data: {len(image_bytes)} bytes, mime: {mime_type}")

                        # Try to optimize with PIL
                        optimized = False
                        try:
                            from PIL import Image
                            import io

                            img = Image.open(io.BytesIO(image_bytes))
                            img.load()  # Force load to verify

                            if img.mode in ('RGBA', 'P'):
                                img = img.convert('RGB')

                            # Resize if larger than 800x800
                            max_size = (800, 800)
                            img.thumbnail(max_size, Image.Resampling.LANCZOS)

                            buffer = io.BytesIO()
                            img.save(buffer, format="JPEG", quality=85, optimize=True)
                            image_bytes = buffer.getvalue()
                            optimized = True
                            print(f"    Optimized to {len(image_bytes)} bytes")

                        except Exception as e:
                            print(f"    PIL optimization skipped: {e}")
                            # Keep original image_bytes - they may still be valid for browser

                        # Return base64 for browser display
                        result_b64 = base64.b64encode(image_bytes).decode('utf-8')
                        print(f"    ✅ Generated {'(optimized)' if optimized else '(raw)'}: {len(result_b64)} chars base64")
                        return result_b64

            print("    ❌ No image in response")
            return None

        except Exception as e:
            print(f"    ❌ Transform error: {e}")
            return None

    async def generate_single_room_visual(
        self,
        original_image_b64: str,
        room_type: str,
        style: str = "modern"
    ) -> dict:
        """Transform a single room image."""
        prompt = f"Transform into a beautifully renovated {style} {room_type}. Fresh, modern, magazine-quality."

        generated = await self._transform_image(original_image_b64, prompt, room_type)

        return {
            "original_image": original_image_b64,
            "generated_image": generated,
            "room_type": room_type,
            "style": style,
        }
