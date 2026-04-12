"""
Executor — AirGuard AI

Routes approved intents to the correct tool module.
All file/system operations go through OpenClaw (self.pc).

ARCHITECTURE RULE: This class is ONLY called by Enforcer.
Never call Executor directly from outside the enforcement layer.
"""

import os
import time
from typing import Dict, Any

from openclaw import Computer
from models import ExecutionResult

# ── Tool registry ────────────────────────────────────────────────────────────
from tools import analyze_aqi as _t_analyze_aqi
from tools import generate_report as _t_generate_report
from tools import send_alert as _t_send_alert
from tools import fetch_live_aqi as _t_fetch_live_aqi
from tools import compare_cities as _t_compare_cities
from tools import pollution_trend as _t_pollution_trend
from tools import health_advisory as _t_health_advisory

_TOOL_REGISTRY: Dict[str, Any] = {
    "analyze_aqi":     _t_analyze_aqi,
    "generate_report": _t_generate_report,
    "send_alert":      _t_send_alert,
    "fetch_live_aqi":  _t_fetch_live_aqi,
    "compare_cities":  _t_compare_cities,
    "pollution_trend": _t_pollution_trend,
    "health_advisory": _t_health_advisory,
}
# ─────────────────────────────────────────────────────────────────────────────


class Executor:
    """
    Dispatches approved intents to tool modules.

    Each tool lives in tools/<action>.py and exposes:
        run(params: dict, context: dict) -> dict

    The context dict carries shared resources (OpenClaw instance, directories)
    so tools never need to import them directly.
    """

    def __init__(self, data_dir: str = "data", output_dir: str = "output"):
        self.pc = Computer()
        self.data_dir = data_dir
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    # ── Shared context passed to every tool ──────────────────────────────────
    @property
    def _context(self) -> Dict[str, Any]:
        return {
            "pc": self.pc,
            "data_dir": self.data_dir,
            "output_dir": self.output_dir,
        }

    # ── Main dispatch entry point ─────────────────────────────────────────────
    def execute(self, intent) -> ExecutionResult:
        """
        Route an approved intent to its tool and return an ExecutionResult.
        Called exclusively by Enforcer — never directly.
        """
        start = time.time()
        action = intent.action.lower()
        params = intent.parameters

        tool = _TOOL_REGISTRY.get(action)
        if tool is None:
            return ExecutionResult(
                success=False,
                message=(
                    f"Unknown action '{action}'. "
                    f"Supported: {', '.join(_TOOL_REGISTRY)}"
                ),
                data=None,
                execution_time=time.time() - start,
            )

        try:
            result_data = tool.run(params, self._context)

            if "error" in result_data:
                return ExecutionResult(
                    success=False,
                    message=result_data["error"],
                    data=result_data,
                    execution_time=time.time() - start,
                )

            files_created = []
            if "report_file" in result_data:
                files_created.append(result_data["report_file"])

            return ExecutionResult(
                success=True,
                message=self._success_message(action, params),
                data=result_data,
                execution_time=time.time() - start,
                files_created=files_created,
            )

        except FileNotFoundError as exc:
            return ExecutionResult(
                success=False,
                message=f"File not found: {exc}",
                data=None,
                execution_time=time.time() - start,
            )
        except PermissionError as exc:
            return ExecutionResult(
                success=False,
                message=f"Permission denied: {exc}",
                data=None,
                execution_time=time.time() - start,
            )
        except Exception as exc:
            return ExecutionResult(
                success=False,
                message=f"Execution error: {exc}",
                data=None,
                execution_time=time.time() - start,
            )

    # ── Backward-compat helpers (used by existing tests / demo scripts) ───────
    def read_pollution_data(self, location: str) -> Dict[str, Any]:
        """Read raw pollution data via OpenClaw. Kept for backward compatibility."""
        import json, csv
        from io import StringIO

        loc = location.lower().replace(" ", "_")
        json_path = os.path.join(self.data_dir, f"{loc}_pollution.json")
        csv_path = os.path.join(self.data_dir, f"{loc}_pollution.csv")

        try:
            return json.loads(self.pc.read_file(json_path))
        except FileNotFoundError:
            content = self.pc.read_file(csv_path)
            from datetime import datetime
            return {
                "location": location,
                "data": list(csv.DictReader(StringIO(content))),
                "timestamp": datetime.now().isoformat(),
            }

    def analyze_aqi(self, location: str) -> Dict[str, Any]:
        """Backward-compat wrapper — delegates to analyze_aqi tool."""
        result = _t_analyze_aqi.run({"location": location}, self._context)
        if "error" in result:
            raise ValueError(result["error"])
        return result

    def generate_report(self, analysis: Dict[str, Any], location: str = None) -> Dict[str, Any]:
        """Backward-compat wrapper — delegates to generate_report tool."""
        loc = location or analysis.get("location", "Unknown")
        result = _t_generate_report.run({"location": loc}, self._context)
        if "error" in result:
            raise IOError(result["error"])
        return result

    def send_alert(self, severity: str, message: str,
                   area: str = None, pollutants: Dict[str, float] = None) -> Dict[str, Any]:
        """Backward-compat wrapper — delegates to send_alert tool."""
        result = _t_send_alert.run(
            {"severity": severity, "message": message,
             "area": area, "pollutants": pollutants},
            self._context,
        )
        if "error" in result:
            raise ValueError(result["error"])
        return result

    # ── Internal helpers ──────────────────────────────────────────────────────
    @staticmethod
    def _success_message(action: str, params: Dict[str, Any]) -> str:
        loc = params.get("location", "")
        messages = {
            "generate_report": f"Pollution report generated for {loc}",
            "analyze_aqi":     f"AQI analysis completed for {loc}",
            "send_alert":      f"Alert dispatched (severity: {params.get('severity', 'warning')})",
            "fetch_live_aqi":  f"Live AQI fetched for {loc}",
            "compare_cities":  "City comparison completed",
            "pollution_trend": f"Pollution trend analysed for {loc}",
            "health_advisory": f"Health advisory generated for {loc}",
        }
        return messages.get(action, f"Action '{action}' completed")
