"""
Formats alerts for display.
This module contains testable formatting logic.
"""

from datetime import datetime


class AlertFormatter:
    """Formats alerts for display."""

    @staticmethod
    def format_alert(alert: dict[str, str]) -> str:
        """Format a single alert for console output."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        product = alert.get("product", "Unknown Product")
        status = alert.get("status", "unknown").upper()
        description = alert.get("description", "")

        alert_msg = f"[{timestamp}] Product: {product}"
        if description:
            alert_msg += f" | Status: {status} - {description}"
        else:
            alert_msg += f" | Status: {status}"

        return alert_msg
