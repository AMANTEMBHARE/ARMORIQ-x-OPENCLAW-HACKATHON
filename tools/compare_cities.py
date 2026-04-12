"""
Tool: compare_cities
Compares AQI across multiple cities and returns a ranked summary.
Uses fetch_live_aqi internally so it stays consistent.
"""

from typing import Dict, Any, List
from datetime import datetime
from tools import fetch_live_aqi as live_tool


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compare AQI across cities.

    params:
        cities (list[str]): cities to compare (default: all available)
        location (str): single city — treated as primary if cities not provided
    context:
        (unused)
    """
    cities: List[str] = params.get("cities") or []

    # If no explicit list, fall back to location param or compare all defaults
    if not cities:
        loc = params.get("location")
        if loc:
            cities = [loc]
        else:
            cities = ["Delhi", "Mumbai", "Bangalore", "Chennai", "Kolkata"]

    results = []
    errors = []

    for city in cities:
        data = live_tool.run({"location": city}, context)
        if "error" in data:
            errors.append(data["error"])
        else:
            results.append({
                "city": data["location"],
                "aqi": data["aqi"],
                "health_label": data["health_label"],
                "pm25": data["pollutants"]["PM2.5"],
            })

    if not results:
        return {"error": "Could not fetch data for any city", "details": errors}

    # Rank worst → best
    ranked = sorted(results, key=lambda x: x["aqi"], reverse=True)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i

    best = ranked[-1]
    worst = ranked[0]

    insight = (
        f"{worst['city']} has the worst air quality (AQI {worst['aqi']} — {worst['health_label']}). "
        f"{best['city']} is the cleanest (AQI {best['aqi']} — {best['health_label']})."
    )

    return {
        "timestamp": datetime.now().isoformat(),
        "cities_compared": len(ranked),
        "ranking": ranked,
        "insight": insight,
        "errors": errors if errors else None,
    }
