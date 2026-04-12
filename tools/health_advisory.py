"""
Tool: health_advisory

Returns detailed, actionable health guidance based on current AQI.
Fetches live AQI first, then maps it to group-specific advice.
"""

from typing import Dict, Any
from datetime import datetime
from tools import fetch_live_aqi as live_tool


# Detailed advice per AQI band, per population group
_ADVICE: Dict[str, Dict[str, Any]] = {
    "Good": {
        "range": "0-50",
        "color": "Green",
        "general": "Air quality is satisfactory. Enjoy outdoor activities.",
        "groups": {
            "General public":    "No restrictions. Good day for outdoor exercise.",
            "Children":          "Safe for outdoor play and sports.",
            "Elderly":           "No special precautions needed.",
            "Heart/lung patients": "No restrictions.",
            "Athletes":          "Ideal conditions for training outdoors.",
        },
        "mask_needed": False,
        "outdoor_ok":  True,
    },
    "Moderate": {
        "range": "51-100",
        "color": "Yellow",
        "general": "Acceptable air quality. Unusually sensitive people should consider limiting prolonged outdoor exertion.",
        "groups": {
            "General public":    "Acceptable for most. Sensitive individuals may feel mild effects.",
            "Children":          "Generally safe. Watch for any respiratory symptoms.",
            "Elderly":           "Limit prolonged strenuous outdoor activity.",
            "Heart/lung patients": "Consider reducing prolonged outdoor exertion.",
            "Athletes":          "Reduce intensity of prolonged outdoor workouts.",
        },
        "mask_needed": False,
        "outdoor_ok":  True,
    },
    "Unhealthy for Sensitive Groups": {
        "range": "101-150",
        "color": "Orange",
        "general": "Sensitive groups may experience health effects. General public is less likely to be affected.",
        "groups": {
            "General public":    "Unusually sensitive people should reduce prolonged outdoor exertion.",
            "Children":          "Limit prolonged outdoor play. Watch for coughing or shortness of breath.",
            "Elderly":           "Avoid prolonged outdoor exertion. Stay indoors if possible.",
            "Heart/lung patients": "Avoid prolonged outdoor exertion. Keep medication handy.",
            "Athletes":          "Move training indoors or reduce duration significantly.",
        },
        "mask_needed": True,
        "outdoor_ok":  False,
    },
    "Unhealthy": {
        "range": "151-200",
        "color": "Red",
        "general": "Everyone may begin to experience health effects. Sensitive groups may experience more serious effects.",
        "groups": {
            "General public":    "Avoid prolonged outdoor exertion. Take breaks indoors.",
            "Children":          "Keep indoors. No outdoor sports or play.",
            "Elderly":           "Stay indoors. Close windows.",
            "Heart/lung patients": "Stay indoors. Avoid all outdoor physical activity.",
            "Athletes":          "Cancel outdoor training. Train indoors only.",
        },
        "mask_needed": True,
        "outdoor_ok":  False,
    },
    "Very Unhealthy": {
        "range": "201-300",
        "color": "Purple",
        "general": "Health alert — everyone may experience serious health effects.",
        "groups": {
            "General public":    "Avoid all outdoor activities. Stay indoors with windows closed.",
            "Children":          "Do not go outside. Keep school windows closed.",
            "Elderly":           "Stay indoors. Use air purifier if available.",
            "Heart/lung patients": "Stay indoors. Seek medical advice if symptoms worsen.",
            "Athletes":          "No outdoor activity. Rest and stay hydrated indoors.",
        },
        "mask_needed": True,
        "outdoor_ok":  False,
    },
    "Hazardous": {
        "range": "300+",
        "color": "Maroon",
        "general": "EMERGENCY CONDITIONS. Everyone is affected. Avoid all outdoor exposure.",
        "groups": {
            "General public":    "Stay indoors. Seal gaps in windows/doors. Use N95 mask if evacuation needed.",
            "Children":          "Do not go outside under any circumstances.",
            "Elderly":           "Stay indoors. Call doctor if experiencing breathing difficulty.",
            "Heart/lung patients": "Emergency — contact healthcare provider immediately if symptomatic.",
            "Athletes":          "No physical activity of any kind outdoors.",
        },
        "mask_needed": True,
        "outdoor_ok":  False,
    },
}


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Return health advisory for a city based on its current AQI.

    params:
        location (str): city name
    context:
        pc, data_dir (passed through to fetch_live_aqi)
    """
    location: str = params.get("location", "Delhi").strip().title()

    # Get current AQI (live or fallback)
    aqi_data = live_tool.run({"location": location}, context)
    if "error" in aqi_data:
        return aqi_data

    aqi: int = aqi_data["aqi"]
    health_label: str = aqi_data["health_label"]
    advice = _ADVICE.get(health_label, _ADVICE["Moderate"])

    return {
        "location":      location,
        "timestamp":     datetime.now().isoformat(),
        "current_aqi":   aqi,
        "health_label":  health_label,
        "aqi_range":     advice["range"],
        "color_code":    advice["color"],
        "general":       advice["general"],
        "mask_needed":   advice["mask_needed"],
        "outdoor_ok":    advice["outdoor_ok"],
        "by_group":      advice["groups"],
        "source":        aqi_data.get("source", "unknown"),
    }
