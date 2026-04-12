"""
Tool: pollution_trend

Analyses the AQI trend from local historical data for a city.
Shows hourly/daily movement, direction, and a plain-English summary.
"""

import os
import json
import csv
from io import StringIO
from typing import Dict, Any, List
from datetime import datetime


def _health_label(aqi: float) -> str:
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Moderate"
    if aqi <= 150:  return "Unhealthy for Sensitive Groups"
    if aqi <= 200:  return "Unhealthy"
    if aqi <= 300:  return "Very Unhealthy"
    return "Hazardous"


def _trend_arrow(direction: str) -> str:
    return {"improving": "↓ Improving", "worsening": "↑ Worsening", "stable": "→ Stable"}.get(direction, "?")


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyse AQI trend for a location from local data files.

    params:
        location (str): city name
    context:
        pc: openclaw.Computer
        data_dir (str)
    """
    location: str = params.get("location", "Delhi").strip().title()
    pc = context["pc"]
    data_dir: str = context["data_dir"]

    loc_key = location.lower().replace(" ", "_")
    rows: List[Dict] = []

    # Load data — try JSON then CSV
    for ext in ("json", "csv"):
        path = os.path.join(data_dir, f"{loc_key}_pollution.{ext}")
        try:
            content = pc.read_file(path)
            if ext == "json":
                raw = json.loads(content)
                rows = raw.get("data", [])
            else:
                rows = list(csv.DictReader(StringIO(content)))
            if rows:
                break
        except FileNotFoundError:
            continue

    if not rows:
        return {"error": f"No historical data found for '{location}'"}

    # Extract AQI series
    aqi_series: List[float] = []
    labels: List[str] = []

    for r in rows:
        for key in ["aqi", "AQI"]:
            if key in r:
                try:
                    aqi_series.append(float(r[key]))
                    label = r.get("time") or r.get("date") or str(len(aqi_series))
                    labels.append(label)
                    break
                except (ValueError, TypeError):
                    pass

    if len(aqi_series) < 2:
        return {"error": f"Not enough data points to calculate trend for '{location}'"}

    # Stats
    avg = round(sum(aqi_series) / len(aqi_series), 1)
    peak = round(max(aqi_series), 1)
    lowest = round(min(aqi_series), 1)
    peak_time = labels[aqi_series.index(max(aqi_series))]
    low_time  = labels[aqi_series.index(min(aqi_series))]

    # Direction: compare first third vs last third
    third = max(1, len(aqi_series) // 3)
    first_avg = sum(aqi_series[:third]) / third
    last_avg  = sum(aqi_series[-third:]) / third
    diff_pct  = ((last_avg - first_avg) / first_avg) * 100

    if diff_pct > 5:
        direction = "worsening"
    elif diff_pct < -5:
        direction = "improving"
    else:
        direction = "stable"

    # Build readable data points list
    data_points = [
        {"time": labels[i], "aqi": aqi_series[i], "label": _health_label(aqi_series[i])}
        for i in range(len(aqi_series))
    ]

    summary = (
        f"AQI in {location} is {_trend_arrow(direction)} "
        f"(avg {avg}, peak {peak} at {peak_time}, lowest {lowest} at {low_time}). "
        f"Overall health status: {_health_label(avg)}."
    )

    return {
        "location":    location,
        "timestamp":   datetime.now().isoformat(),
        "direction":   direction,
        "trend_label": _trend_arrow(direction),
        "stats": {
            "average_aqi": avg,
            "peak_aqi":    peak,
            "peak_time":   peak_time,
            "lowest_aqi":  lowest,
            "lowest_time": low_time,
            "change_pct":  round(diff_pct, 1),
            "readings":    len(aqi_series),
        },
        "data_points": data_points,
        "summary":     summary,
        "health_label": _health_label(avg),
    }
