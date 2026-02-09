"""
UK Renovation Cost Estimation Engine
Based on 2024 UK renovation costs with London/regional adjustments
"""
from typing import Dict, List, Optional
import re


# Regional price multipliers (UK average = 1.0)
REGIONAL_MULTIPLIERS = {
    "london": 1.35,
    "south_east": 1.15,
    "south_west": 1.05,
    "east": 1.05,
    "west_midlands": 0.95,
    "east_midlands": 0.90,
    "yorkshire": 0.90,
    "north_west": 0.90,
    "north_east": 0.85,
    "wales": 0.85,
    "scotland": 0.90,
    "northern_ireland": 0.85,
}

# UK Renovation Cost Database (2024 - UK average, before regional adjustment)
UK_COSTS = {
    # Kitchen costs
    "kitchen": {
        "full_replacement": {"low": 12000, "mid": 20000, "high": 40000},  # Complete new kitchen fitted
        "cabinet_replacement": {"low": 6000, "mid": 10000, "high": 18000},
        "worktop_replacement": {"low": 1500, "mid": 3000, "high": 6000},  # Full worktop
        "appliances_budget": {"low": 2000, "mid": 4000, "high": 8000},  # Full set
        "flooring": {"low": 800, "mid": 1500, "high": 3000},  # Typical kitchen
        "tiling_splashback": {"low": 400, "mid": 800, "high": 1500},
    },

    # Bathroom costs (complete room)
    "bathroom": {
        "full_replacement": {"low": 6000, "mid": 10000, "high": 20000},  # Complete new bathroom
        "suite_only": {"low": 1500, "mid": 3000, "high": 6000},
        "retile_full": {"low": 1500, "mid": 3000, "high": 5000},
        "flooring": {"low": 400, "mid": 800, "high": 1500},
    },

    # Per sqm costs for general rooms
    "per_sqm": {
        "replaster_walls": {"low": 25, "mid": 40, "high": 60},
        "paint_walls_ceiling": {"low": 12, "mid": 20, "high": 35},
        "flooring_carpet": {"low": 25, "mid": 45, "high": 80},
        "flooring_laminate": {"low": 35, "mid": 60, "high": 100},
        "flooring_engineered": {"low": 70, "mid": 110, "high": 180},
        "flooring_solid": {"low": 100, "mid": 160, "high": 280},
    },

    # Whole house essentials (based on typical 3-bed ~85sqm)
    "whole_house": {
        "full_rewire": {"low": 4500, "mid": 7000, "high": 12000},  # 3-bed
        "rewire_per_sqm": {"low": 55, "mid": 85, "high": 140},  # For larger properties
        "consumer_unit": {"low": 500, "mid": 800, "high": 1200},
        "new_boiler_combi": {"low": 2500, "mid": 4000, "high": 6500},
        "new_boiler_system": {"low": 3500, "mid": 5500, "high": 8500},
        "central_heating_full": {"low": 5000, "mid": 8000, "high": 14000},  # Boiler + rads
        "radiator_per_unit": {"low": 300, "mid": 500, "high": 900},
    },

    # Windows & Doors
    "windows_doors": {
        "window_upvc": {"low": 500, "mid": 800, "high": 1400},  # Per window installed
        "window_sash_repair": {"low": 400, "mid": 700, "high": 1200},
        "window_sash_replace": {"low": 1500, "mid": 2500, "high": 4000},
        "front_door_composite": {"low": 1200, "mid": 2000, "high": 4000},  # Fitted
        "front_door_timber": {"low": 2000, "mid": 3500, "high": 6000},
        "internal_door_fitted": {"low": 250, "mid": 400, "high": 700},
    },

    # Structural
    "structural": {
        "remove_wall_non_load": {"low": 800, "mid": 1500, "high": 3000},
        "remove_wall_load_bearing": {"low": 3000, "mid": 5500, "high": 10000},
        "steelwork_rsj": {"low": 1500, "mid": 2500, "high": 4500},
        "underpin_per_meter": {"low": 1500, "mid": 2500, "high": 4000},
        "damp_proof_course": {"low": 3000, "mid": 5000, "high": 9000},
    },

    # External/Facade
    "external": {
        "roof_repair_minor": {"low": 500, "mid": 1500, "high": 3000},
        "roof_repair_major": {"low": 3000, "mid": 6000, "high": 12000},
        "roof_replace_full": {"low": 8000, "mid": 14000, "high": 25000},
        "repoint_brickwork_full": {"low": 3000, "mid": 5000, "high": 9000},
        "render_full_house": {"low": 5000, "mid": 8000, "high": 14000},
        "guttering_full": {"low": 800, "mid": 1500, "high": 3000},
        "fascias_soffits": {"low": 2000, "mid": 3500, "high": 6000},
        "chimney_repair": {"low": 500, "mid": 1200, "high": 2500},
        "chimney_rebuild": {"low": 2000, "mid": 4000, "high": 7000},
    },

    # Garden/Landscaping
    "garden": {
        "basic_clearance": {"low": 500, "mid": 1000, "high": 2000},
        "landscaping_basic": {"low": 2000, "mid": 4000, "high": 8000},
        "landscaping_full": {"low": 5000, "mid": 10000, "high": 25000},
        "fencing_full": {"low": 1500, "mid": 3000, "high": 6000},
        "patio_new": {"low": 2000, "mid": 4000, "high": 8000},
        "driveway": {"low": 3000, "mid": 6000, "high": 12000},
    },
}

# Default room sizes if not provided (in sqm)
DEFAULT_ROOM_SIZES = {
    "kitchen": 12,
    "bathroom": 5,
    "ensuite": 4,
    "bedroom": 12,
    "living_room": 18,
    "dining_room": 14,
    "hallway": 8,
    "study": 9,
    "utility": 4,
    "garden": 50,
    "garage": 15,
    "conservatory": 12,
    "exterior": 0,  # Not a room
}


class CostEngine:
    """Calculate renovation costs based on property analysis."""

    def __init__(self, region: str = None):
        self.region = region.lower() if region else "uk_average"
        self.multiplier = REGIONAL_MULTIPLIERS.get(self.region, 1.0)
        self.costs = UK_COSTS

    def _apply_multiplier(self, cost_dict: dict) -> dict:
        """Apply regional multiplier to costs."""
        return {
            level: int(cost_dict[level] * self.multiplier)
            for level in ["low", "mid", "high"]
        }

    def _detect_region(self, address: str) -> tuple[str, float]:
        """Detect region from address and return (region_name, multiplier)."""
        address_lower = address.lower()

        # London detection (postcodes and area names)
        london_indicators = [
            "london", ", sw1", ", sw2", ", sw3", ", sw4", ", sw5", ", sw6", ", sw7", ", sw8", ", sw9",
            ", se1", ", se2", ", se3", ", se4", ", se5", ", se6", ", se7", ", se8", ", se9",
            ", nw1", ", nw2", ", nw3", ", nw4", ", nw5", ", nw6", ", nw7", ", nw8", ", nw9", ", nw10",
            ", n1", ", n2", ", n3", ", n4", ", n5", ", n6", ", n7", ", n8", ", n9", ", n10",
            ", e1", ", e2", ", e3", ", e4", ", e5", ", e6", ", e7", ", e8", ", e9", ", e10",
            ", w1", ", w2", ", w3", ", w4", ", w5", ", w6", ", w7", ", w8", ", w9", ", w10",
            ", ec1", ", ec2", ", ec3", ", ec4", ", wc1", ", wc2"
        ]
        if any(x in address_lower for x in london_indicators):
            return "london", REGIONAL_MULTIPLIERS["london"]

        # Northern Ireland
        ni_indicators = ["belfast", "northern ireland", ", bt", "antrim", "derry", "londonderry",
                         "lisburn", "newry", "bangor", "armagh", "omagh", "enniskillen", "coleraine"]
        if any(x in address_lower for x in ni_indicators):
            return "northern_ireland", REGIONAL_MULTIPLIERS["northern_ireland"]

        # Scotland
        scotland_indicators = ["scotland", "edinburgh", "glasgow", "aberdeen", "dundee", "inverness",
                               "stirling", "perth", ", eh", ", g1", ", g2", ", ab", ", dd", ", iv", ", fk"]
        if any(x in address_lower for x in scotland_indicators):
            return "scotland", REGIONAL_MULTIPLIERS["scotland"]

        # Wales
        wales_indicators = ["wales", "cardiff", "swansea", "newport", "wrexham", "bangor",
                           ", cf", ", sa", ", np", ", ll", ", sy"]
        if any(x in address_lower for x in wales_indicators):
            return "wales", REGIONAL_MULTIPLIERS["wales"]

        # North East
        ne_indicators = ["newcastle", "sunderland", "durham", "middlesbrough", "gateshead",
                        ", ne1", ", ne2", ", sr", ", ts", ", dl"]
        if any(x in address_lower for x in ne_indicators):
            return "north_east", REGIONAL_MULTIPLIERS["north_east"]

        # North West
        nw_indicators = ["manchester", "liverpool", "preston", "blackpool", "bolton", "wigan",
                        ", m1", ", m2", ", l1", ", l2", ", pr", ", bl", ", wn"]
        if any(x in address_lower for x in nw_indicators):
            return "north_west", REGIONAL_MULTIPLIERS["north_west"]

        # Yorkshire
        yorks_indicators = ["leeds", "sheffield", "bradford", "york", "hull", "doncaster",
                          ", ls", ", s1", ", s2", ", bd", ", yo", ", hu", ", dn"]
        if any(x in address_lower for x in yorks_indicators):
            return "yorkshire", REGIONAL_MULTIPLIERS["yorkshire"]

        # West Midlands
        wm_indicators = ["birmingham", "coventry", "wolverhampton", "dudley", "walsall",
                        ", b1", ", b2", ", cv", ", wv", ", dy", ", ws"]
        if any(x in address_lower for x in wm_indicators):
            return "west_midlands", REGIONAL_MULTIPLIERS["west_midlands"]

        # East Midlands
        em_indicators = ["nottingham", "leicester", "derby", "lincoln", "northampton",
                        ", ng", ", le", ", de", ", ln", ", nn"]
        if any(x in address_lower for x in em_indicators):
            return "east_midlands", REGIONAL_MULTIPLIERS["east_midlands"]

        # South East (not London)
        se_indicators = ["brighton", "southampton", "portsmouth", "oxford", "reading", "milton keynes",
                        "guildford", "canterbury", "maidstone", ", bn", ", so", ", po", ", ox", ", rg", ", mk", ", gu", ", ct", ", me"]
        if any(x in address_lower for x in se_indicators):
            return "south_east", REGIONAL_MULTIPLIERS["south_east"]

        # South West
        sw_indicators = ["bristol", "exeter", "plymouth", "bath", "bournemouth", "cheltenham",
                        ", bs", ", ex", ", pl", ", ba", ", bh", ", gl"]
        if any(x in address_lower for x in sw_indicators):
            return "south_west", REGIONAL_MULTIPLIERS["south_west"]

        # East of England
        east_indicators = ["cambridge", "norwich", "ipswich", "colchester", "peterborough",
                          ", cb", ", nr", ", ip", ", co", ", pe"]
        if any(x in address_lower for x in east_indicators):
            return "east", REGIONAL_MULTIPLIERS["east"]

        # Default to UK average
        return "uk_average", 1.0

    def calculate(self, room_analyses: dict, property_data: dict) -> dict:
        """Calculate complete renovation cost breakdown."""

        # Detect region from address
        address = property_data.get("address", "")
        self.region, self.multiplier = self._detect_region(address)

        # Get property size
        total_sqm = self._get_total_sqm(room_analyses, property_data)
        bedrooms = property_data.get("bedrooms", 3)
        bathrooms = property_data.get("bathrooms", 1)

        # Determine overall condition
        overall = room_analyses.get("overall_assessment", {})
        avg_condition = overall.get("average_condition", 5)

        breakdown = {
            "property_info": {
                "total_sqm": total_sqm,
                "total_sqft": int(total_sqm * 10.764),
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "region": self.region,
                "region_display": self.region.replace("_", " ").title(),
                "price_multiplier": self.multiplier,
                "is_london": self.region == "london",
            },
            "by_room": {},
            "by_category": {
                "Kitchen": {"low": 0, "mid": 0, "high": 0},
                "Bathrooms": {"low": 0, "mid": 0, "high": 0},
                "Electrical": {"low": 0, "mid": 0, "high": 0},
                "Plumbing & Heating": {"low": 0, "mid": 0, "high": 0},
                "Windows & Doors": {"low": 0, "mid": 0, "high": 0},
                "External/Facade": {"low": 0, "mid": 0, "high": 0},
                "Decoration": {"low": 0, "mid": 0, "high": 0},
                "Flooring": {"low": 0, "mid": 0, "high": 0},
                "Garden": {"low": 0, "mid": 0, "high": 0},
                "Structural": {"low": 0, "mid": 0, "high": 0},
            },
            "essential_works": [],
            "recommended_works": [],
            "optional_works": [],
            "total": {"low": 0, "mid": 0, "high": 0},
        }

        # Process each room analysis
        rooms_analyzed = []
        for room_key, analysis in room_analyses.items():
            if room_key in ["floorplan_analysis", "overall_assessment"]:
                continue
            if not isinstance(analysis, dict) or "error" in analysis:
                continue

            rooms_analyzed.append(analysis)
            room_costs = self._process_room(room_key, analysis, breakdown)
            if room_costs["total"]["mid"] > 0:
                breakdown["by_room"][room_key] = room_costs

        # Add whole-house essentials based on condition
        self._add_whole_house_costs(breakdown, avg_condition, total_sqm, bedrooms, rooms_analyzed)

        # Calculate totals
        for cat_costs in breakdown["by_category"].values():
            for level in ["low", "mid", "high"]:
                breakdown["total"][level] += cat_costs[level]

        # Remove empty categories
        breakdown["by_category"] = {
            k: v for k, v in breakdown["by_category"].items()
            if v["mid"] > 0
        }

        # Add contingency (10-15% based on condition)
        contingency_rate = 0.10 if avg_condition > 5 else 0.15 if avg_condition > 3 else 0.20
        breakdown["contingency"] = {
            level: int(breakdown["total"][level] * contingency_rate)
            for level in ["low", "mid", "high"]
        }
        breakdown["contingency_rate"] = f"{int(contingency_rate * 100)}%"

        # Grand total
        breakdown["grand_total"] = {
            level: breakdown["total"][level] + breakdown["contingency"][level]
            for level in ["low", "mid", "high"]
        }

        # Cost per sqm/sqft
        if total_sqm > 0:
            breakdown["cost_per_sqm"] = {
                level: int(breakdown["grand_total"][level] / total_sqm)
                for level in ["low", "mid", "high"]
            }
            breakdown["cost_per_sqft"] = {
                level: int(breakdown["grand_total"][level] / (total_sqm * 10.764))
                for level in ["low", "mid", "high"]
            }

        # Generate summary
        breakdown["summary"] = self._generate_summary(breakdown, avg_condition)

        return breakdown

    def _get_total_sqm(self, room_analyses: dict, property_data: dict) -> float:
        """Get total property size in sqm."""
        # Try floorplan first
        floorplan = room_analyses.get("floorplan_analysis", {})
        if floorplan and floorplan.get("total_sqm"):
            return float(floorplan["total_sqm"])

        # Try property data sqft
        sqft = property_data.get("sqft", 0)
        if sqft > 0:
            return sqft / 10.764

        # Estimate from bedrooms
        bedrooms = property_data.get("bedrooms", 3)
        # Rough UK estimate: 50sqm base + 15sqm per bedroom
        return 50 + (bedrooms * 15)

    def _process_room(self, room_key: str, analysis: dict, breakdown: dict) -> dict:
        """Process a single room's renovation needs."""
        room_type = analysis.get("room_type", "other")
        condition = analysis.get("condition_score", 5)
        renovation_items = analysis.get("renovation_items", [])

        room_size = DEFAULT_ROOM_SIZES.get(room_type, 12)

        room_costs = {
            "room_type": room_type,
            "condition": condition,
            "items": [],
            "total": {"low": 0, "mid": 0, "high": 0}
        }

        # Process specific renovation items
        for item in renovation_items:
            item_cost = self._calculate_item_cost(item, room_type, room_size, breakdown)
            if item_cost:
                room_costs["items"].append(item_cost)
                for level in ["low", "mid", "high"]:
                    room_costs["total"][level] += item_cost["cost"][level]

        # Add general room refresh if condition is poor and no specific items
        if condition <= 5 and len(room_costs["items"]) == 0:
            refresh_cost = self._calculate_room_refresh(room_type, room_size, condition, breakdown)
            room_costs["items"].append(refresh_cost)
            for level in ["low", "mid", "high"]:
                room_costs["total"][level] += refresh_cost["cost"][level]

        return room_costs

    def _calculate_item_cost(self, item: dict, room_type: str, room_size: float, breakdown: dict) -> Optional[dict]:
        """Calculate cost for a specific renovation item."""
        item_name = item.get("item", "").lower()
        priority = item.get("priority", "recommended")
        scope = item.get("scope", "replace")

        cost = None
        category = "Decoration"
        description = item.get("item", "General works")

        # Kitchen
        if room_type == "kitchen" and any(x in item_name for x in ["kitchen", "cabinet", "unit", "worktop"]):
            if scope == "replace" or "replace" in item_name:
                cost = self._apply_multiplier(self.costs["kitchen"]["full_replacement"])
            else:
                cost = self._apply_multiplier(self.costs["kitchen"]["cabinet_replacement"])
            category = "Kitchen"

        # Bathroom
        elif room_type in ["bathroom", "ensuite"] and any(x in item_name for x in ["bathroom", "suite", "shower", "bath"]):
            cost = self._apply_multiplier(self.costs["bathroom"]["full_replacement"])
            category = "Bathrooms"

        # Windows
        elif "window" in item_name:
            if "sash" in item_name:
                cost = self._apply_multiplier(self.costs["windows_doors"]["window_sash_replace"])
            else:
                cost = self._apply_multiplier(self.costs["windows_doors"]["window_upvc"])
            category = "Windows & Doors"

        # Doors
        elif "door" in item_name:
            if "front" in item_name or "external" in item_name:
                cost = self._apply_multiplier(self.costs["windows_doors"]["front_door_composite"])
            else:
                cost = self._apply_multiplier(self.costs["windows_doors"]["internal_door_fitted"])
            category = "Windows & Doors"

        # External/Facade
        elif any(x in item_name for x in ["render", "facade", "brickwork", "repoint", "pointing"]):
            if "repoint" in item_name or "pointing" in item_name:
                cost = self._apply_multiplier(self.costs["external"]["repoint_brickwork_full"])
            else:
                cost = self._apply_multiplier(self.costs["external"]["render_full_house"])
            category = "External/Facade"

        elif any(x in item_name for x in ["roof", "gutter", "fascia", "soffit"]):
            if "replace" in item_name or "new" in item_name:
                cost = self._apply_multiplier(self.costs["external"]["roof_replace_full"])
            else:
                cost = self._apply_multiplier(self.costs["external"]["roof_repair_major"])
            category = "External/Facade"

        # Electrical
        elif any(x in item_name for x in ["electri", "wiring", "rewire"]):
            cost = self._apply_multiplier(self.costs["whole_house"]["full_rewire"])
            category = "Electrical"

        # Plumbing/Heating
        elif any(x in item_name for x in ["boiler", "heating", "radiator", "plumbing"]):
            if "boiler" in item_name:
                cost = self._apply_multiplier(self.costs["whole_house"]["new_boiler_combi"])
            else:
                cost = self._apply_multiplier(self.costs["whole_house"]["central_heating_full"])
            category = "Plumbing & Heating"

        # Flooring
        elif any(x in item_name for x in ["floor", "carpet"]):
            sqm_cost = self._apply_multiplier(self.costs["per_sqm"]["flooring_laminate"])
            cost = {level: sqm_cost[level] * room_size for level in ["low", "mid", "high"]}
            category = "Flooring"

        # Plastering/Walls
        elif any(x in item_name for x in ["plaster", "wall", "crack"]):
            sqm_cost = self._apply_multiplier(self.costs["per_sqm"]["replaster_walls"])
            cost = {level: int(sqm_cost[level] * room_size) for level in ["low", "mid", "high"]}
            category = "Decoration"

        # Painting
        elif any(x in item_name for x in ["paint", "decorat"]):
            sqm_cost = self._apply_multiplier(self.costs["per_sqm"]["paint_walls_ceiling"])
            cost = {level: int(sqm_cost[level] * room_size) for level in ["low", "mid", "high"]}
            category = "Decoration"

        # Garden
        elif any(x in item_name for x in ["garden", "landscap", "patio", "fence"]):
            cost = self._apply_multiplier(self.costs["garden"]["landscaping_basic"])
            category = "Garden"

        # Structural
        elif any(x in item_name for x in ["structural", "underpin", "subsidence", "damp"]):
            if "damp" in item_name:
                cost = self._apply_multiplier(self.costs["structural"]["damp_proof_course"])
            else:
                cost = self._apply_multiplier(self.costs["structural"]["underpin_per_meter"])
                cost = {level: cost[level] * 3 for level in ["low", "mid", "high"]}  # Estimate 3m
            category = "Structural"

        if cost:
            # Add to category totals
            for level in ["low", "mid", "high"]:
                breakdown["by_category"][category][level] += cost[level]

            # Add to priority lists
            work_item = {"description": description, "cost": cost}
            if priority == "essential":
                breakdown["essential_works"].append(work_item)
            elif priority == "optional":
                breakdown["optional_works"].append(work_item)
            else:
                breakdown["recommended_works"].append(work_item)

            return {
                "description": description,
                "priority": priority,
                "category": category,
                "cost": cost
            }

        return None

    def _calculate_room_refresh(self, room_type: str, room_size: float, condition: int, breakdown: dict) -> dict:
        """Calculate general refresh costs for a room."""
        if condition <= 3:
            # Major refresh
            plaster = self._apply_multiplier(self.costs["per_sqm"]["replaster_walls"])
            paint = self._apply_multiplier(self.costs["per_sqm"]["paint_walls_ceiling"])
            floor = self._apply_multiplier(self.costs["per_sqm"]["flooring_laminate"])
            cost = {
                level: int((plaster[level] + paint[level] + floor[level]) * room_size)
                for level in ["low", "mid", "high"]
            }
            desc = "Full room refresh (replaster, paint, new flooring)"
        else:
            # Light refresh
            paint = self._apply_multiplier(self.costs["per_sqm"]["paint_walls_ceiling"])
            cost = {
                level: int(paint[level] * room_size * 1.5)  # Walls + ceiling
                for level in ["low", "mid", "high"]
            }
            desc = "Decoration refresh"

        for level in ["low", "mid", "high"]:
            breakdown["by_category"]["Decoration"][level] += cost[level]

        return {
            "description": desc,
            "priority": "recommended",
            "category": "Decoration",
            "cost": cost
        }

    def _add_whole_house_costs(self, breakdown: dict, avg_condition: float, total_sqm: float, bedrooms: int, rooms_analyzed: list):
        """Add whole-house essential costs based on condition."""

        # Check if we've seen exterior issues
        has_exterior_issues = any(
            r.get("room_type") == "exterior" and r.get("condition_score", 10) < 5
            for r in rooms_analyzed
        )

        # For derelict/poor condition properties, add essential whole-house works
        if avg_condition <= 3:
            # Full rewire likely needed
            if breakdown["by_category"]["Electrical"]["mid"] == 0:
                rewire = self._apply_multiplier(self.costs["whole_house"]["full_rewire"])
                # Scale for larger properties
                if total_sqm > 100:
                    rewire_sqm = self._apply_multiplier(self.costs["whole_house"]["rewire_per_sqm"])
                    rewire = {level: int(rewire_sqm[level] * total_sqm) for level in ["low", "mid", "high"]}

                for level in ["low", "mid", "high"]:
                    breakdown["by_category"]["Electrical"][level] += rewire[level]
                breakdown["essential_works"].append({"description": "Full electrical rewire", "cost": rewire})

            # New heating system likely needed
            if breakdown["by_category"]["Plumbing & Heating"]["mid"] == 0:
                heating = self._apply_multiplier(self.costs["whole_house"]["central_heating_full"])
                for level in ["low", "mid", "high"]:
                    breakdown["by_category"]["Plumbing & Heating"][level] += heating[level]
                breakdown["essential_works"].append({"description": "New central heating system", "cost": heating})

            # Windows likely need replacing
            if breakdown["by_category"]["Windows & Doors"]["mid"] == 0:
                # Estimate windows based on bedrooms
                num_windows = 4 + (bedrooms * 2)
                window_cost = self._apply_multiplier(self.costs["windows_doors"]["window_upvc"])
                total_windows = {level: window_cost[level] * num_windows for level in ["low", "mid", "high"]}

                # Add front door
                door_cost = self._apply_multiplier(self.costs["windows_doors"]["front_door_composite"])
                for level in ["low", "mid", "high"]:
                    total_windows[level] += door_cost[level]
                    breakdown["by_category"]["Windows & Doors"][level] += total_windows[level]

                breakdown["essential_works"].append({"description": f"Replace {num_windows} windows + front door", "cost": total_windows})

        # Add external works if exterior is in poor condition
        if has_exterior_issues and breakdown["by_category"]["External/Facade"]["mid"] == 0:
            external_cost = self._apply_multiplier(self.costs["external"]["render_full_house"])
            gutters = self._apply_multiplier(self.costs["external"]["guttering_full"])
            for level in ["low", "mid", "high"]:
                total = external_cost[level] + gutters[level]
                breakdown["by_category"]["External/Facade"][level] += total
            breakdown["essential_works"].append({
                "description": "External facade repair & guttering",
                "cost": {level: external_cost[level] + gutters[level] for level in ["low", "mid", "high"]}
            })

    def _generate_summary(self, breakdown: dict, avg_condition: float) -> List[dict]:
        """Generate human-readable summary."""
        summary = []
        total = breakdown["grand_total"]["mid"]
        sqm = breakdown["property_info"]["total_sqm"]

        # Project scale
        if total < 15000:
            summary.append({"type": "info", "text": "Light renovation - mainly cosmetic updates"})
        elif total < 40000:
            summary.append({"type": "info", "text": "Moderate renovation project"})
        elif total < 80000:
            summary.append({"type": "warning", "text": "Major renovation - consider phased approach"})
        else:
            summary.append({"type": "warning", "text": "Extensive renovation - professional project management recommended"})

        # Cost per sqm context
        cost_per_sqm = breakdown.get("cost_per_sqm", {}).get("mid", 0)
        if cost_per_sqm > 0:
            if cost_per_sqm < 400:
                summary.append({"type": "info", "text": f"£{cost_per_sqm}/sqm - light refurbishment level"})
            elif cost_per_sqm < 800:
                summary.append({"type": "info", "text": f"£{cost_per_sqm}/sqm - standard renovation level"})
            elif cost_per_sqm < 1200:
                summary.append({"type": "warning", "text": f"£{cost_per_sqm}/sqm - significant works required"})
            else:
                summary.append({"type": "warning", "text": f"£{cost_per_sqm}/sqm - major structural/systems work"})

        # Essential works warning
        if breakdown["essential_works"]:
            essential_total = sum(w["cost"]["mid"] for w in breakdown["essential_works"])
            summary.append({
                "type": "warning",
                "text": f"Essential works: £{essential_total:,} (must be done before habitation)"
            })

        # Biggest cost area
        by_cat = breakdown["by_category"]
        if by_cat:
            biggest = max(by_cat.keys(), key=lambda k: by_cat[k]["mid"])
            summary.append({
                "type": "detail",
                "text": f"Largest cost: {biggest} (£{by_cat[biggest]['mid']:,})"
            })

        return summary
