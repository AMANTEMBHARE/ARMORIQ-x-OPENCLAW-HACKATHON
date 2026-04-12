"""
Tool: fetch_live_aqi

Fetches REAL live AQI from aqicn.org (World Air Quality Index project).
Free API — get a token at https://aqicn.org/data-platform/token/

Set your token:
    $env:AQICN_TOKEN="your_token_here"   (PowerShell)
    export AQICN_TOKEN=your_token_here   (bash)

Falls back to local data files if:
  - No token is set
  - API is unreachable / rate-limited
  - City not found on the API
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any
from datetime import datetime

# City name -> aqicn station slug (works without a token too for basic lookup)
_CITY_SLUGS: Dict[str, str] = {
    "Delhi":     "delhi",
    "Mumbai":    "mumbai",
    "Bangalore": "bangalore",
    "Chennai":   "chennai",
    "Kolkata":   "kolkata",
    "Hyderabad": "hyderabad",
    "Pune":      "pune",
    "Ahmedabad": "ahmedabad",
    "Jaipur":    "jaipur",
    "Lucknow":   "lucknow",
}

# Fallback static data used when API is unavailable
_FALLBACK: Dict[str, Dict[str, Any]] = {
    "Delhi":     {"aqi": 287, "pm25": 145, "pm10": 320, "no2": 68,  "so2": 15, "co": 1.2},
    "Mumbai":    {"aqi": 156, "pm25": 78,  "pm10": 185, "no2": 45,  "so2": 12, "co": 0.8},
    "Bangalore": {"aqi": 98,  "pm25": 49,  "pm10": 72,  "no2": 28,  "so2": 9,  "co": 0.6},
    "Chennai":   {"aqi": 112, "pm25": 56,  "pm10": 84,  "no2": 33,  "so2": 11, "co": 0.7},
    "Kolkata":   {"aqi": 198, "pm25": 99,  "pm10": 148, "no2": 55,  "so2": 18, "co": 1.1},
    "Hyderabad": {"aqi": 121, "pm25": 61,  "pm10": 95,  "no2": 37,  "so2": 13, "co": 0.75},
    "Pune":      {"aqi": 108, "pm25": 54,  "pm10": 88,  "no2": 31,  "so2": 10, "co": 0.65},
    "Ahmedabad": {"aqi": 145, "pm25": 72,  "pm10": 118, "no2": 43,  "so2": 16, "co": 0.95},
    "Jaipur":    {"aqi": 163, "pm25": 82,  "pm10": 135, "no2": 49,  "so2": 17, "co": 1.0},
    "Lucknow":   {"aqi": 221, "pm25": 111, "pm10": 198, "no2": 61,  "so2": 21, "co": 1.3},
}


def _health_label(aqi: int) -> str:
    if aqi <= 50:   return "Good"
    if aqi <= 100:  return "Moderate"
    if aqi <= 150:  return "Unhealthy for Sensitive Groups"
    if aqi <= 200:  return "Unhealthy"
    if aqi <= 300:  return "Very Unhealthy"
    return "Hazardous"


def _fetch_from_api(city_slug: str, token: str) -> Dict[str, Any]:
    """
    Call aqicn.org API and return parsed data.
    Raises on any network or parse error so caller can fall back.
    """
    url = f"https://api.waqi.info/feed/{city_slug}/?token={token}"
    req = urllib.request.Request(url, headers={"User-Agent": "AirGuardAI/1.0"})

    with urllib.request.urlopen(req, timeout=5) as resp:
        body = json.loads(resp.read().decode())

    if body.get("status") != "ok":
        raise ValueError(f"API returned status: {body.get('status')}")

    d = body["data"]
    iaqi = d.get("iaqi", {})

    def _val(key: str) -> float:
        entry = iaqi.get(key)
        return round(float(entry["v"]), 2) if entry else 0.0

    return {
        "aqi":  int(d["aqi"]),
        "pm25": _val("pm25"),
        "pm10": _val("pm10"),
        "no2":  _val("no2"),
        "so2":  _val("so2"),
        "co":   _val("co"),
        "source": "aqicn.org (live)",
        "station": d.get("city", {}).get("name", city_slug),
    }


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return live AQI for a city.

    Tries aqicn.org API first (if AQICN_TOKEN env var is set),
    then falls back to local data files, then to built-in static values.

    params:
        location (str): city name
    context:
        pc: openclaw.Computer (used for local file fallback)
        data_dir (str)
    """
    location: str = params.get("location", "Delhi").strip().title()

    if location not in _FALLBACK:
        supported = ", ".join(sorted(_FALLBACK.keys()))
        return {"error": f"City '{location}' not supported. Available: {supported}"}

    token = os.environ.get("AQICN_TOKEN", "").strip()
    source_used = "fallback"
    reading: Dict[str, Any] = {}

    # ── 1. Try live API ───────────────────────────────────────────────────────
    if token:
        slug = _CITY_SLUGS.get(location, location.lower())
        try:
            reading = _fetch_from_api(slug, token)
            source_used = reading.get("source", "aqicn.org (live)")
        except Exception as api_err:
            print(f"[fetch_live_aqi] API failed ({api_err}), trying local file...")

    # ── 2. Try local data file ────────────────────────────────────────────────
    if not reading:
        try:
            import csv
            from io import StringIO

            pc = context.get("pc")
            data_dir = context.get("data_dir", "data")
            loc_key = location.lower().replace(" ", "_")

            for ext, parser in [("json", "json"), ("csv", "csv")]:
                path = os.path.join(data_dir, f"{loc_key}_pollution.{ext}")
                try:
                    content = pc.read_file(path)
                    if ext == "json":
                        raw = json.loads(content)
                        rows = raw.get("data", [])
                    else:
                        rows = list(csv.DictReader(StringIO(content)))

                    if rows:
                        last = rows[-1]

                        def _get(keys):
                            for k in keys:
                                if k in last:
                                    try: return float(last[k])
                                    except: pass
                            return 0.0

                        reading = {
                            "aqi":  int(_get(["aqi", "AQI"])),
                            "pm25": _get(["pm25", "PM2.5", "pm2.5"]),
                            "pm10": _get(["pm10", "PM10"]),
                            "no2":  _get(["no2",  "NO2"]),
                            "so2":  _get(["so2",  "SO2"]),
                            "co":   _get(["co",   "CO"]),
                            "source": f"local file ({ext})",
                        }
                        source_used = reading["source"]
                        break
                except FileNotFoundError:
                    continue
        except Exception as file_err:
            print(f"[fetch_live_aqi] Local file failed ({file_err}), using static fallback...")

    # ── 3. Static fallback ────────────────────────────────────────────────────
    if not reading:
        fb = _FALLBACK[location]
        reading = {**fb, "source": "static fallback (set AQICN_TOKEN for live data)"}
        source_used = reading["source"]

    aqi = reading["aqi"]
    return {
        "location":     location,
        "timestamp":    datetime.now().isoformat(),
        "aqi":          aqi,
        "health_label": _health_label(aqi),
        "pollutants": {
            "PM2.5": reading.get("pm25", 0),
            "PM10":  reading.get("pm10", 0),
            "NO2":   reading.get("no2",  0),
            "SO2":   reading.get("so2",  0),
            "CO":    reading.get("co",   0),
        },
        "source": source_used,
    }
