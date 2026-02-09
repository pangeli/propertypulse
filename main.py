"""
PropertyPulse API - AI-powered property renovation analyzer
Single-page app with SSE streaming for real-time progress
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl
from typing import Optional, AsyncGenerator
import uuid
import asyncio
import json
import sqlite3
from datetime import datetime

app = FastAPI(
    title="PropertyPulse",
    description="AI-powered property renovation analysis using Gemini 3",
    version="1.0.0"
)

# Initialize SQLite database
def init_db():
    conn = sqlite3.connect('data/property_pulse.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS analyses (
            job_id TEXT PRIMARY KEY,
            url TEXT,
            status TEXT,
            results TEXT,
            created_at TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# Templates
templates = Jinja2Templates(directory="templates")

# Database helpers
def save_job(job_id: str, data: dict):
    conn = sqlite3.connect('data/property_pulse.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO analyses (job_id, url, status, results, created_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (
        job_id,
        data.get('url'),
        data.get('status'),
        json.dumps(data.get('results')) if data.get('results') else None,
        datetime.now()
    ))
    conn.commit()
    conn.close()

def get_job(job_id: str):
    conn = sqlite3.connect('data/property_pulse.db')
    c = conn.cursor()
    c.execute('SELECT * FROM analyses WHERE job_id = ?', (job_id,))
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            "job_id": row[0],
            "url": row[1],
            "status": row[2],
            "results": json.loads(row[3]) if row[3] else None,
            "created_at": row[4]
        }
    return None

def get_recent_jobs(limit: int = 10):
    conn = sqlite3.connect('data/property_pulse.db')
    c = conn.cursor()
    c.execute('''
        SELECT job_id, url, status, results, created_at 
        FROM analyses 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    
    jobs = []
    for row in rows:
        job = {
            "job_id": row[0],
            "url": row[1],
            "status": row[2],
            "created_at": row[4],
            "address": "Processing..."
        }
        
        # Try to extract address from results if available
        if row[3]:
            try:
                res = json.loads(row[3])
                if res and "property" in res:
                    job["address"] = res["property"].get("address", "Unknown Address")
                    job["price"] = res["property"].get("price_text", "")
                    # We avoid sending full base64 images in the list view for performance
            except:
                pass
        
        jobs.append(job)
    return jobs

def delete_job(job_id: str):
    conn = sqlite3.connect('data/property_pulse.db')
    c = conn.cursor()
    c.execute('DELETE FROM analyses WHERE job_id = ?', (job_id,))
    conn.commit()
    conn.close()
    
    # Also remove from memory if active
    if job_id in active_jobs:
        del active_jobs[job_id]
    
    return True

# In-memory store for active streaming events (still needed for SSE)
active_jobs: dict = {}


class AnalyzeRequest(BaseModel):
    url: HttpUrl
    generate_visuals: bool = True


class RefineRequest(BaseModel):
    prompt: str
    style: str = "modern"


# Helper to format SSE messages
def sse_message(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"


@app.get("/jobs/recent")
async def get_recent():
    """Get list of recent analyses."""
    return get_recent_jobs()


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Serve the main page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/analyze")
async def start_analysis(request: AnalyzeRequest):
    """Start a new analysis job and return job ID."""
    job_id = str(uuid.uuid4())[:8]

    # Save initial state to DB
    save_job(job_id, {
        "status": "pending",
        "url": str(request.url),
        "results": None
    })

    # Store in memory for SSE streaming
    active_jobs[job_id] = {
        "status": "pending",
        "url": str(request.url),
        "generate_visuals": request.generate_visuals,
        "events": asyncio.Queue(),
        "results": None
    }

    # Start analysis in background
    asyncio.create_task(run_analysis_with_streaming(job_id))

    return {"job_id": job_id, "status": "started"}


@app.post("/analyze/{job_id}/refine/{room_key}")
async def refine_image(job_id: str, room_key: str, request: RefineRequest):
    """Refine a generated image with a new prompt."""
    
    # 1. Get job
    job = None
    if job_id in active_jobs:
        job = active_jobs[job_id]
        results = job.get("results")
    else:
        db_job = get_job(job_id)
        if db_job:
            results = db_job.get("results")
            # If loaded from DB, structure it like active job for uniform handling locally
            job = {
                "job_id": job_id,
                "url": db_job["url"],
                "results": results,
                "status": db_job["status"]
            }
        else:
            raise HTTPException(status_code=404, detail="Job not found")

    if not results or "after_images" not in results:
        raise HTTPException(status_code=400, detail="No analysis results found")
        
    # 2. Get original image
    after_images = results.get("after_images", {})
    target_image = after_images.get(room_key)
    
    if not target_image:
        raise HTTPException(status_code=404, detail="Room visualization not found")
        
    original_b64 = target_image.get("original_image")
    if not original_b64:
        raise HTTPException(status_code=400, detail="Original image missing")

    # 3. Regenerate
    try:
        from src.image_gen import RenovationVisualizer
        visualizer = RenovationVisualizer()

        # We use the raw _transform_image which takes the prompt directly
        generated_b64 = await visualizer._transform_image(
            original_b64, 
            request.prompt, 
            target_image.get("room_type", "room"),
            request.style
        )
        
        if not generated_b64:
             raise HTTPException(status_code=500, detail="Failed to generate image")
             
        # 4. Update results
        target_image["generated_image"] = generated_b64
        target_image["renovation_description"] = request.prompt
        
        # Update in memory if active
        if job_id in active_jobs:
            active_jobs[job_id]["results"]["after_images"][room_key] = target_image
            
        # Update DB
        save_job(job_id, {
            "url": job["url"],
            "status": job["status"],
            "results": results
        })
        
        return {
            "status": "success",
            "generated_image": generated_b64,
            "renovation_description": request.prompt
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/analyze/{job_id}/stream")
async def stream_analysis(job_id: str):
    """SSE endpoint for streaming analysis progress."""
    if job_id not in active_jobs:
        # Check if job exists in DB but not in memory (finished/reloaded)
        db_job = get_job(job_id)
        if db_job and db_job['status'] == 'complete':
             # Immediately send completion event
            async def instant_generator():
                yield sse_message({"type": "complete", "results": db_job['results']})
            return StreamingResponse(instant_generator(), media_type="text/event-stream")
        
        raise HTTPException(status_code=404, detail="Job not found or expired")

    async def event_generator() -> AsyncGenerator[str, None]:
        job = active_jobs[job_id]

        while True:
            try:
                # Wait for next event with timeout
                event = await asyncio.wait_for(job["events"].get(), timeout=60.0)
                yield sse_message(event)

                # Stop if complete or error
                if event.get("type") in ["complete", "error"]:
                    break
            except asyncio.TimeoutError:
                # Send keepalive
                yield sse_message({"type": "keepalive"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.delete("/analyze/{job_id}")
async def delete_analysis(job_id: str):
    """Delete an analysis job."""
    delete_job(job_id)
    return {"status": "deleted"}


@app.get("/analyze/{job_id}")
async def get_analysis(job_id: str):
    """Get analysis results (polling/persistence fallback)."""
    # Try active jobs first
    if job_id in active_jobs:
        job = active_jobs[job_id]
        if job["results"]:
            return {"status": "complete", **job["results"]}
        elif job["status"] == "error":
             return {"status": "error", "error": job.get("error", "Unknown error")}
        else:
            return {"status": "processing"}

    # Fallback to DB
    db_job = get_job(job_id)
    if db_job:
        if db_job["results"]:
            return {"status": "complete", **db_job["results"]}
        elif db_job["status"] == "error":
            return {"status": "error", "error": "Analysis failed"}
        else:
            return {"status": "processing"}

    raise HTTPException(status_code=404, detail="Job not found")


async def run_analysis_with_streaming(job_id: str):
    """Run the full analysis pipeline with SSE streaming."""
    job = active_jobs[job_id]
    queue = job["events"]
    url = job["url"]
    generate_visuals = job["generate_visuals"]

    async def send(event_type: str, **kwargs):
        await queue.put({"type": event_type, **kwargs})

    async def reason(step_type: str, title: str, detail: str = None):
        """Send a reasoning step to the UI."""
        await send("reasoning", step_type=step_type, title=title, detail=detail)

    try:
        # ===== STAGE 1: SCRAPING =====
        await send("progress", stage="Connecting to Rightmove...", progress=5)
        await reason("thinking", "Initializing extraction pipeline", "Launching headless browser to fetch listing data...")

        # Initialize scraper
        from src.scraper import RightmoveScraper
        scraper = RightmoveScraper()

        await reason("analyzing", "Fetching property listing", f"Target: {url[:50]}...")
        property_data = await scraper.scrape(url)

        if not property_data:
            raise Exception("Failed to scrape property - page may be unavailable")

        # Send property info
        await send("property_info", data={
            "address": property_data.get("address"),
            "price": property_data.get("price_text"),
            "bedrooms": property_data.get("bedrooms"),
            "bathrooms": property_data.get("bathrooms")
        })

        num_images = len(property_data.get("images", {}))
        await reason("success", f"Property identified",
                    f"{property_data.get('address')} - {property_data.get('price_text')}")

        # Strategic reasoning about the task
        await reason("strategy", f"Planning analysis for {num_images} images",
                    f"Will assess: room types, condition scores, renovation requirements")

        await send("progress", stage="Analyzing property photos...", progress=15)

        # ===== STAGE 2: ROOM ANALYSIS =====
        await reason("thinking", "Activating Gemini 3 Flash vision model",
                    "Multi-modal analysis for room identification and condition assessment...")

        # Initialize analyzer
        from src.analyzer import PropertyAnalyzer
        analyzer = PropertyAnalyzer()

        room_analyses = {}
        images = property_data.get("images", {})
        total_images = len(images)

        for i, (room_key, image_data) in enumerate(images.items()):
            progress = 15 + int((i / max(total_images, 1)) * 40)
            await send("progress", stage=f"Analyzing room {i+1}/{total_images}...", progress=progress)

            await reason("analyzing", f"Analyzing image {i+1}/{total_images}",
                        f"Examining: {image_data.get('label', room_key)}")

            try:
                # Add delay between requests
                if i > 0:
                    await asyncio.sleep(1)

                analysis = await analyzer._analyze_room_image(
                    image_data.get("base64"),
                    image_data.get("label", room_key)
                )

                if analysis and "error" not in analysis:
                    room_analyses[room_key] = analysis
                    room_type = analysis.get("room_type", "room")
                    condition = analysis.get("condition_score", 5)
                    issues = analysis.get("issues", [])

                    # Stream the ACTUAL AI reasoning from Gemini
                    ai_reasoning = analysis.get("reasoning", "")
                    if ai_reasoning:
                        # Truncate at sentence boundary if too long
                        if len(ai_reasoning) > 200:
                            # Find last sentence end before 200 chars
                            truncated = ai_reasoning[:250]
                            last_period = truncated.rfind('.')
                            if last_period > 100:
                                ai_reasoning = truncated[:last_period + 1]
                            else:
                                # No good sentence break, truncate at word
                                last_space = truncated.rfind(' ')
                                ai_reasoning = truncated[:last_space] + "..."

                        await reason("thinking", f"{room_type.replace('_', ' ').title()}",
                                    ai_reasoning)

                    # Result summary - show condition label and top issue
                    condition_label = "Poor" if condition <= 3 else "Fair" if condition <= 5 else "Good" if condition <= 7 else "Great"
                    if issues:
                        await reason("success", f"{room_type.replace('_', ' ').title()}: {condition_label}",
                                    issues[0])
                    else:
                        await reason("success", f"{room_type.replace('_', ' ').title()}: {condition_label}",
                                    "No major issues detected")

                    # Show priority work if any
                    reno_items = analysis.get("renovation_items", [])
                    essential = [r["item"] for r in reno_items if r.get("priority") == "essential"]
                    if essential:
                        await reason("decision", f"Priority work",
                                    essential[0])
                else:
                    await reason("warning", f"Skipping image {i+1}",
                                "Unable to analyze - may be unclear or floorplan")

            except Exception as e:
                await reason("error", f"Analysis failed for image {i+1}", str(e)[:100])

        # Generate overall assessment
        room_analyses["overall_assessment"] = analyzer._generate_overall_assessment(
            room_analyses, property_data
        )

        overall = room_analyses.get("overall_assessment", {})
        avg_condition = overall.get("average_condition", 5)
        scope = overall.get("renovation_scope", "moderate")

        await reason("strategy", f"Property assessment complete",
                    f"Average condition: {avg_condition}/10 | Scope: {scope.replace('_', ' ')}")

        # ===== STAGE 3: COST CALCULATION =====
        await send("progress", stage="Calculating renovation costs...", progress=60)
        await reason("thinking", "Initializing cost estimation engine",
                    "Loading UK 2024 pricing data with regional adjustments...")

        from src.cost_engine import CostEngine
        cost_engine = CostEngine()

        cost_breakdown = cost_engine.calculate(room_analyses, property_data)

        total_mid = cost_breakdown.get("grand_total", {}).get("mid", 0)
        cost_sqm = cost_breakdown.get("cost_per_sqm", {}).get("mid", 0)

        # Get region info for pricing context
        prop_info = cost_breakdown.get("property_info", {})
        region_display = prop_info.get("region_display", "UK")
        price_mult = prop_info.get("price_multiplier", 1.0)

        if price_mult > 1:
            region_note = f"{region_display} pricing (+{int((price_mult - 1) * 100)}%)"
        elif price_mult < 1:
            region_note = f"{region_display} pricing ({int((price_mult - 1) * 100)}%)"
        else:
            region_note = f"{region_display} (UK average pricing)"

        await reason("cost", f"Total estimate: £{total_mid:,}",
                    f"{region_note} | £{cost_sqm}/sqm incl. contingency")

        # Strategic cost breakdown
        by_cat = cost_breakdown.get("by_category", {})
        if by_cat:
            sorted_cats = sorted(by_cat.items(), key=lambda x: x[1]["mid"], reverse=True)
            if len(sorted_cats) >= 2:
                await reason("decision", f"Largest investments: {sorted_cats[0][0]} & {sorted_cats[1][0]}",
                            f"£{sorted_cats[0][1]['mid']:,} + £{sorted_cats[1][1]['mid']:,}")
            elif sorted_cats:
                await reason("decision", f"Primary investment: {sorted_cats[0][0]}",
                            f"£{sorted_cats[0][1]['mid']:,}")

        # Essential works warning
        essential_works = cost_breakdown.get("essential_works", [])
        if essential_works:
            essential_total = sum(w["cost"]["mid"] for w in essential_works)
            await reason("warning", f"Essential works: £{essential_total:,}",
                        f"{len(essential_works)} items required before habitation")

        # ===== STAGE 4: VISUALIZATION =====
        after_images = {}
        if generate_visuals:
            await send("progress", stage="Generating renovation visualizations...", progress=70)
            await reason("thinking", "Activating Nano Banana Pro image model",
                        "Preparing style-aware renovation transformations...")

            from src.image_gen import RenovationVisualizer
            visualizer = RenovationVisualizer()

            # Prioritize exterior > living > kitchen > bedroom > bathroom
            rooms_to_visualize = {}
            priorities = {
                "exterior": 1, "front": 1, "facade": 1, "garden": 1,
                "living_room": 2, "sitting_room": 2, "lounge": 2, "reception": 2,
                "kitchen": 3, "dining_room": 3,
                "bedroom": 4,
                "bathroom": 5, "shower_room": 5, "wc": 5
            }
            
            # Find best candidate for each priority category
            # Map priority level (1-5) to list of (score, key, val)
            candidates_by_priority = {1: [], 2: [], 3: [], 4: [], 5: []}
            others = []

            for k, v in room_analyses.items():
                if not isinstance(v, dict) or k in ["overall_assessment", "floorplan_analysis"]:
                    continue
                
                room_type = v.get("room_type", "").lower()
                condition = v.get("condition_score", 10)
                
                # Check priority
                priority = None
                for key, p in priorities.items():
                    if key in room_type:
                        priority = p
                        break
                
                if priority:
                    candidates_by_priority[priority].append((condition, k, v))
                elif condition < 7: # Only add low condition non-priority rooms
                    others.append((condition, k, v))

            # Select 1 best candidate (lowest condition) for each priority level
            final_selection = []
            
            for p in range(1, 6):
                candidates = candidates_by_priority[p]
                if candidates:
                    # Sort by condition (ascending) to pick worst condition first
                    candidates.sort(key=lambda x: x[0])
                    # Add the best one
                    final_selection.append(candidates[0])

            # Fill remaining slots with next worst condition rooms (from others or remaining priority candidates)
            # Combine unused priority candidates and others
            remaining = []
            for p in range(1, 6):
                if len(candidates_by_priority[p]) > 1:
                    remaining.extend(candidates_by_priority[p][1:]) # Skip the first one which was taken
            remaining.extend(others)
            
            # Sort remaining by condition
            remaining.sort(key=lambda x: x[0])
            
            # Add to final selection up to limit (increased to 5)
            VIZ_LIMIT = 5
            slots_left = VIZ_LIMIT - len(final_selection)
            
            if slots_left > 0:
                final_selection.extend(remaining[:slots_left])
            
            # Convert back to dict for processing loop, preserving order
            rooms_to_process = [(item[1], item[2]) for item in final_selection]

            total_viz = len(rooms_to_process)
            viz_count = 0

            # Show AI's room selection decision
            if rooms_to_process:
                selected_types = [item[2].get("room_type", "room").replace("_", " ") for item in final_selection[:3]]
                await reason("decision", f"Selected {total_viz} rooms for visualization",
                            f"Priority: {', '.join(selected_types)}{'...' if total_viz > 3 else ''}")

            for room_key, analysis in rooms_to_process:
                if viz_count >= VIZ_LIMIT: 
                    break

                room_type = analysis.get("room_type", "room")
                original = property_data.get("images", {}).get(room_key, {})
                original_b64 = original.get("base64")

                if not original_b64:
                    continue

                progress = 70 + int((viz_count / max(total_viz, 1)) * 25)
                await send("progress", stage=f"Generating visualization {viz_count+1}...", progress=progress)

                # Detect architectural style for strategic approach
                style = visualizer._detect_architectural_style(analysis)
                if style in ["victorian", "georgian"]:
                    style_strategy = "Preserving period character"
                elif style == "1930s":
                    style_strategy = "Respecting art deco features"
                else:
                    style_strategy = "Applying modern aesthetic"

                await reason("strategy", f"Styling approach: {style_strategy}",
                            f"Generating {room_type.replace('_', ' ')} visualization...")

                try:
                    reno_prompt = visualizer._create_renovation_prompt(room_type, analysis)
                    generated_b64 = await visualizer._transform_image(
                        original_b64, reno_prompt, room_type, style
                    )

                    if generated_b64:
                        after_images[room_key] = {
                            "room_type": room_type,
                            "original_image": original_b64,
                            "generated_image": generated_b64,
                            "renovation_description": reno_prompt,
                            "original_condition": analysis.get("condition_score", 5)
                        }
                        await reason("image", f"{room_type.replace('_', ' ').title()} transformed",
                                    f"Before/after slider ready")
                        viz_count += 1
                    else:
                        await reason("warning", f"Skipped {room_type}",
                                    "Image generation unavailable for this room")

                except Exception as e:
                    await reason("error", f"Visualization error", str(e)[:100])

                # Rate limiting
                await asyncio.sleep(2)

        # ===== COMPLETE =====
        await send("progress", stage="Analysis complete!", progress=100)
        num_viz = len(after_images)
        await reason("success", "Analysis pipeline complete",
                    f"{len(room_analyses)-1} rooms analyzed | £{total_mid:,} estimate | {num_viz} visualizations")

        # Store results
        results = {
            "property": {
                "address": property_data.get("address"),
                "price": property_data.get("price"),
                "price_text": property_data.get("price_text"),
                "bedrooms": property_data.get("bedrooms"),
                "bathrooms": property_data.get("bathrooms"),
                "sqft": property_data.get("sqft"),
                "property_type": property_data.get("property_type")
            },
            "analysis": room_analyses,
            "costs": cost_breakdown,
            "after_images": after_images
        }

        job["results"] = results
        job["status"] = "complete"

        # Save final results to DB
        save_job(job_id, {
            "url": url,
            "status": "complete",
            "results": results
        })

        await send("complete", results=results)

    except Exception as e:
        import traceback
        traceback.print_exc()
        job["status"] = "error"
        job["error"] = str(e)
        
        # Update DB with error
        save_job(job_id, {
            "url": url,
            "status": "error",
            "results": None
        })
        
        await reason("error", "Analysis failed", str(e))
        await send("error", message=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
