"""
Tool: send_alert
Formats and simulates sending a pollution alert (no real notifications).
"""

from typing import Dict, Any
from datetime import datetime


def run(params: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Simulate sending a pollution alert.

    params:
        severity (str): info | warning | critical
        message (str): alert body
        location (str): affected area (optional)
        pollutants (dict): pollutant levels (optional)
    context:
        (unused — no file I/O needed)
    """
    severity: str = params.get("severity", "warning").lower()
    message: str = params.get("message", "")
    area: str = params.get("area") or params.get("location", "")
    pollutants: Dict[str, float] = params.get("pollutants") or {}

    valid = ["info", "warning", "critical"]
    if severity not in valid:
        return {"error": f"Invalid severity '{severity}'. Must be one of: {valid}"}
    if not message:
        return {"error": "Alert message is required"}

    ts = datetime.now()
    alert_id = f"ALERT-{ts.strftime('%Y%m%d%H%M%S')}"

    lines = [
        "=" * 60,
        f"AIRGUARD AI — POLLUTION ALERT [{severity.upper()}]",
        "=" * 60,
        f"Alert ID  : {alert_id}",
        f"Timestamp : {ts.strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    if area:
        lines.append(f"Area      : {area}")
    lines += ["", "MESSAGE:", message, ""]

    if pollutants:
        lines.append("POLLUTANT LEVELS:")
        for p, v in pollutants.items():
            lines.append(f"  {p}: {v} µg/m³")
        lines.append("")

    lines.append("RECOMMENDED ACTIONS:")
    if severity == "critical":
        lines += [
            "  • STAY INDOORS — do not go outside",
            "  • Close all windows and doors",
            "  • Use air purifiers at maximum setting",
        ]
    elif severity == "warning":
        lines += [
            "  • Limit outdoor activities",
            "  • Sensitive groups should stay indoors",
            "  • Consider wearing masks if going outside",
        ]
    else:
        lines += [
            "  • Be aware of air quality conditions",
            "  • Sensitive individuals should take precautions",
        ]
    lines += ["", "=" * 60]

    formatted = "\n".join(lines)
    print("\n" + formatted + "\n")

    recipients = {
        "critical": ["pollution_control_board", "emergency_services", "health_department", "public_system"],
        "warning": ["pollution_control_board", "health_department", "public_system"],
        "info": ["pollution_control_board", "monitoring_dashboard"],
    }

    return {
        "alert_sent": True,
        "alert_id": alert_id,
        "severity": severity,
        "message": message,
        "area": area or "Not specified",
        "timestamp": ts.isoformat(),
        "recipients": recipients[severity],
        "formatted_alert": formatted,
    }
