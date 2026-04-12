"""
Tool: analyze_aqi
Reads local pollution data and returns statistical analysis.
"""

from typing import Dict, Any
from datetime import datetime


def _health_advisory(avg_aqi: float) -> str:
    if avg_aqi <= 50:
        return "Good - Air quality is satisfactory"
    elif avg_aqi <= 100:
        return "Moderate - Acceptable for most people"
    elif avg_aqi <= 150:
        return "Unhealthy for Sensitive Groups - Limit prolonged outdoor exertion"
    elif avg_aqi <= 200:
        return "Unhealthy - Everyone may experience health effects"
    elif avg_aqi <= 300:
        return "Very Unhealthy - Health alert, avoid outdoor activities"
    return "Hazardous - Emergency conditions, stay indoors"


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze AQI data for a location.

    params:
        location (str): city name
    context:
        pc: openclaw.Computer instance
        data_dir (str): path to data directory
    """
    location: str = params.get("location", "Delhi")
    pc = context["pc"]
    data_dir: str = context["data_dir"]

    import os, json, csv
    from io import StringIO

    loc_key = location.lower().replace(" ", "_")
    json_path = os.path.join(data_dir, f"{loc_key}_pollution.json")
    csv_path = os.path.join(data_dir, f"{loc_key}_pollution.csv")

    # Read data via OpenClaw
    raw_data: Dict[str, Any] = {}
    try:
        content = pc.read_file(json_path)
        raw_data = json.loads(content)
    except FileNotFoundError:
        try:
            content = pc.read_file(csv_path)
            rows = list(csv.DictReader(StringIO(content)))
            raw_data = {"location": location, "data": rows}
        except FileNotFoundError:
            return {"error": f"No data file found for '{location}'"}

    readings = raw_data.get("data", [])
    if not readings:
        return {"error": f"No readings in data for '{location}'"}

    pollutants = ["PM2.5", "PM10", "NO2", "SO2", "CO", "AQI"]
    values: Dict[str, list] = {p: [] for p in pollutants}

    for r in readings:
        for p in pollutants:
            for key in [p, p.lower(), p.replace(".", ""), p.replace(".", "").lower()]:
                if key in r:
                    try:
                        values[p].append(float(r[key]))
                        break
                    except (ValueError, TypeError):
                        pass

    stats: Dict[str, Any] = {}
    for p, vals in values.items():
        if vals:
            stats[p] = {
                "avg": round(sum(vals) / len(vals), 2),
                "min": round(min(vals), 2),
                "max": round(max(vals), 2),
                "count": len(vals),
            }

    aqi_vals = values["AQI"] or [v * 2 for v in values["PM2.5"]]
    if not aqi_vals:
        return {"error": "Insufficient data to calculate AQI"}

    avg_aqi = round(sum(aqi_vals) / len(aqi_vals), 2)

    # Trend: compare first half vs second half
    trend = "insufficient_data"
    if len(aqi_vals) >= 4:
        mid = len(aqi_vals) // 2
        first = sum(aqi_vals[:mid]) / mid
        second = sum(aqi_vals[mid:]) / (len(aqi_vals) - mid)
        diff = ((second - first) / first) * 100
        trend = "worsening" if diff > 5 else ("improving" if diff < -5 else "stable")

    return {
        "location": location,
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "average_aqi": avg_aqi,
            "min_aqi": round(min(aqi_vals), 2),
            "max_aqi": round(max(aqi_vals), 2),
            "trend": trend,
            "readings_count": len(readings),
        },
        "pollutants": {k: v for k, v in stats.items() if k != "AQI"},
        "health_advisory": _health_advisory(avg_aqi),
    }
