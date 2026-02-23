"""
RSS feed parsing for status page incidents.
Extracts incident information from RSS/Atom feeds in an event-based manner.
"""

from typing import Dict, List, Optional
from loguru import logger


class IncidentParser:
    """Parses RSS feed entries to extract incident information."""

    @staticmethod
    def parse_entry(entry: Dict) -> Optional[Dict[str, str]]:
        """
        Parse a single RSS entry into an incident dict.
        
        Args:
            entry: feedparser entry dict
            
        Returns:
            Dict with id, title, status, description, published_at
            or None if entry doesn't contain incident data
        """
        try:
            # Extract fields from RSS entry
            entry_id = entry.get("id", entry.get("link", "unknown"))
            title = entry.get("title", "").strip()
            summary = entry.get("summary", "").strip()
            published = entry.get("published", "")

            if not title:
                return None

            # First try to extract status from description (looks for resolved indicator)
            status_from_desc = IncidentParser._extract_status_from_description(summary)
            if status_from_desc:
                status = status_from_desc
            else:
                # Fall back to extracting from title
                status = IncidentParser._extract_status(title)

            return {
                "id": entry_id,
                "title": title,
                "status": status,
                "description": summary,
                "published_at": published,
            }
        except Exception as e:
            logger.error(f"Error parsing RSS entry: {e}")
            return None

    @staticmethod
    def _extract_status(title: str) -> str:
        """Extract incident status from title."""
        title_lower = title.lower()
        
        # Map keywords to status in priority order
        status_keywords = {
            "resolved": ["resolved"],
            "investigating": ["investigating"],
            "identified": ["identified"],
            "monitoring": ["monitoring"],
            "scheduled": ["scheduled"],
            "degraded": ["degraded", "performance"],
            "outage": ["major outage", "outage"],
        }
        
        for status, keywords in status_keywords.items():
            if any(keyword in title_lower for keyword in keywords):
                return status
        
        return "unknown"

    @staticmethod
    def _extract_status_from_description(description: str) -> str:
        """Extract status from HTML description to detect resolved incidents."""
        desc_lower = description.lower()
        if "<b>status: resolved</b>" in desc_lower:
            return "resolved"
        return "Could not parse status from description"

    @staticmethod
    def filter_active_incidents(entries: List[Dict]) -> List[Dict]:
        """
        Filter out resolved incidents, keep only active ones.
        
        Args:
            entries: List of parsed incident dicts
            
        Returns:
            List of incidents that are not resolved
        """
        return [entry for entry in entries if entry["status"] != "resolved"]

    @staticmethod
    def has_incident_changed(current_incidents: List[Dict], cached_incident_ids: List[str]) -> bool:
        """
        Detect if there are new incidents or status changes.
        
        Args:
            current_incidents: List of current incidents from RSS
            cached_incident_ids: List of previously seen incident IDs
            
        Returns:
            True if there are new incidents or significant changes
        """
        current_ids = {incident["id"] for incident in current_incidents}
        cached_ids = set(cached_incident_ids)

        # New incident detected
        if current_ids - cached_ids:
            return True

        # Incident resolved (removed from feed)
        if cached_ids - current_ids:
            return True

        return False
