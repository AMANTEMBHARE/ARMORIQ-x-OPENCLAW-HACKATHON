"""
Tool: generate_report
Runs AQI analysis then writes a formatted .txt report via OpenClaw.
"""

import os
from typing import Dict, Any
from datetime import datetime
from tools import analyze_aqi as aqi_tool


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a formatted pollution report for a location.

    params:
        location (str): city name
    context:
        pc: openclaw.Computer instance
        data_dir (str)
        output_dir (str)
    """
    location: str = params.get("location", "Delhi")
    pc = context["pc"]
    output_dir: str = context["output_dir"]

    # Reuse analyze_aqi tool — no duplication
    analysis = aqi_tool.run(params, context)
    if "error" in analysis:
        return analysis

    summary = analysis["summary"]
    pollutants = analysis.get("pollutants", {})
    advisory = analysis.get("health_advisory", "")
    avg_aqi = summary.get("average_aqi", 0)

    ts = datetime.now()
    filename = f"{location.lower().replace(' ', '_')}_report_{ts.strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = os.path.join(output_dir, filename)

    lines = [
        "=" * 70,
        "AIRGUARD AI — POLLUTION MONITORING REPORT",
        "=" * 70,
        f"Location      : {location}",
        f"Generated     : {ts.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "─" * 70,
        "SUMMARY",
        "─" * 70,
        f"Average AQI   : {summary.get('average_aqi', 'N/A')}",
        f"Min AQI       : {summary.get('min_aqi', 'N/A')}",
        f"Max AQI       : {summary.get('max_aqi', 'N/A')}",
        f"Trend         : {summary.get('trend', 'N/A').upper()}",
        f"Readings      : {summary.get('readings_count', 'N/A')}",
        "",
    ]

    if pollutants:
        lines += ["─" * 70, "POLLUTANT BREAKDOWN", "─" * 70]
        for p, s in pollutants.items():
            lines += [f"  {p}: avg={s['avg']} µg/m³  min={s['min']}  max={s['max']}"]
        lines.append("")

    lines += [
        "─" * 70,
        "HEALTH ADVISORY",
        "─" * 70,
        advisory,
        "",
        "─" * 70,
        "RECOMMENDATIONS",
        "─" * 70,
    ]

    if avg_aqi > 200:
        lines += [
            "• Stay indoors, keep windows closed",
            "• Use air purifiers at maximum setting",
            "• Wear N95 masks if going outside is necessary",
        ]
    elif avg_aqi > 150:
        lines += [
            "• Limit outdoor activities, especially for sensitive groups",
            "• Consider wearing masks outdoors",
        ]
    elif avg_aqi > 100:
        lines += ["• Sensitive groups should limit prolonged outdoor exertion"]
    else:
        lines += ["• Air quality is acceptable — continue normal activities"]

    lines += ["", "=" * 70, "AirGuard AI — Autonomous Pollution Monitoring", "=" * 70]

    content = "\n".join(lines)

    # Write via OpenClaw
    pc.write_file(filepath, content)
    try:
        pc.open_file(filepath)
    except Exception:
        pass

    return {
        "report_file": filepath,
        "location": location,
        "timestamp": ts.isoformat(),
        "summary": {
            "average_aqi": avg_aqi,
            "trend": summary.get("trend"),
            "health_status": advisory.split(" - ")[0] if " - " in advisory else advisory,
        },
    }
