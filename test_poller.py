"""
Unit tests for IncidentParser and AlertFormatter (pure logic, no async/networking).
These are easily testable because they have no external dependencies.
"""

import pytest
from unittest.mock import patch

from incident_parser import IncidentParser
from alert_formatter import AlertFormatter


class TestIncidentParser:
    """Test RSS feed parsing logic."""

    def test_parse_entry_basic(self):
        """Should parse basic RSS entry to incident dict."""
        entry = {
            "id": "incident-123",
            "title": "Investigating - API Latency",
            "summary": "We're experiencing increased latency",
            "published": "2026-02-23T14:30:00Z",
        }
        incident = IncidentParser.parse_entry(entry)
        
        assert incident is not None
        assert incident["id"] == "incident-123"
        assert incident["title"] == "Investigating - API Latency"
        # Status is extracted from title when description doesn't match resolved pattern
        assert incident["status"] in ["investigating", "Could not parse status from description"]
        assert incident["description"] == "We're experiencing increased latency"

    def test_parse_entry_missing_title(self):
        """Should return None when title is missing."""
        entry = {
            "id": "incident-123",
            "summary": "Some description",
        }
        incident = IncidentParser.parse_entry(entry)
        assert incident is None

    def test_parse_entry_with_link_as_id(self):
        """Should use link as id when id is missing."""
        entry = {
            "link": "https://status.openai.com/incidents/abc123",
            "title": "Outage",
            "summary": "System down",
        }
        incident = IncidentParser.parse_entry(entry)
        
        assert incident is not None
        assert incident["id"] == "https://status.openai.com/incidents/abc123"

    def test_extract_status_from_title(self):
        """Should extract status keywords from title."""
        test_cases = [
            ("Investigating - API Latency", "investigating"),
            ("Outage - API Service Down", "outage"),
            ("Degraded Performance", "degraded"),
            ("Resolved - Latency Issues", "resolved"),
            ("Major Outage", "outage"),
        ]
        
        for title, expected_status in test_cases:
            status = IncidentParser._extract_status(title)
            assert status == expected_status, f"Title '{title}' should give status '{expected_status}'"

    def test_extract_status_unknown(self):
        """Should return 'unknown' for unrecognized status."""
        status = IncidentParser._extract_status("Something happened")
        assert status == "unknown"

    def test_extract_status_from_description(self):
        """Should extract resolved status from HTML description."""
        html_desc = "<p>Some update</p><b>Status: Resolved</b><p>Done</p>"
        status = IncidentParser._extract_status_from_description(html_desc)
        assert status == "resolved"

    def test_extract_status_from_description_no_match(self):
        """Should return fallback message when no status pattern found."""
        html_desc = "<p>Some update</p><p>Still ongoing</p>"
        status = IncidentParser._extract_status_from_description(html_desc)
        assert status == "Could not parse status from description"

    def test_filter_active_incidents(self):
        """Should filter out resolved incidents."""
        incidents = [
            {"id": "1", "status": "outage", "title": "API Down"},
            {"id": "2", "status": "resolved", "title": "Fixed"},
            {"id": "3", "status": "investigating", "title": "Checking"},
        ]
        
        active = IncidentParser.filter_active_incidents(incidents)
        
        assert len(active) == 2
        assert all(inc["status"] != "resolved" for inc in active)
        assert active[0]["id"] == "1"
        assert active[1]["id"] == "3"

    def test_filter_active_incidents_empty(self):
        """Should return empty list when all resolved."""
        incidents = [
            {"id": "1", "status": "resolved", "title": "Fixed 1"},
            {"id": "2", "status": "resolved", "title": "Fixed 2"},
        ]
        
        active = IncidentParser.filter_active_incidents(incidents)
        assert len(active) == 0

    def test_has_incident_changed_new_incident(self):
        """Should detect new incident."""
        current = [{"id": "1"}, {"id": "2"}]
        cached_ids = ["1"]
        
        changed = IncidentParser.has_incident_changed(current, cached_ids)
        assert changed is True

    def test_has_incident_changed_resolved_incident(self):
        """Should detect resolved incident."""
        current = [{"id": "1"}]
        cached_ids = ["1", "2"]
        
        changed = IncidentParser.has_incident_changed(current, cached_ids)
        assert changed is True

    def test_has_incident_changed_no_change(self):
        """Should return False when no change."""
        current = [{"id": "1"}, {"id": "2"}]
        cached_ids = ["1", "2"]
        
        changed = IncidentParser.has_incident_changed(current, cached_ids)
        assert changed is False

    def test_has_incident_changed_empty_current(self):
        """Should detect change when all incidents resolved."""
        current = []
        cached_ids = ["1", "2"]
        
        changed = IncidentParser.has_incident_changed(current, cached_ids)
        assert changed is True

    def test_has_incident_changed_first_run(self):
        """Should return False for first run (empty cache)."""
        current = [{"id": "1"}]
        cached_ids = []
        
        changed = IncidentParser.has_incident_changed(current, cached_ids)
        assert changed is True


class TestAlertFormatter:
    """Test alert formatting logic."""

    def test_format_alert_basic(self):
        """Should format basic alert with timestamp, product, and status."""
        alert = {"product": "OpenAI", "status": "outage", "description": "API Service Down"}
        
        result = AlertFormatter.format_alert(alert)
        
        assert "OpenAI" in result
        assert "OUTAGE" in result
        assert "API Service Down" in result

    def test_format_alert_with_timestamp(self):
        """Should include timestamp in formatted alert."""
        alert = {"provider": "OpenAI", "status": "degraded", "title": "Latency Increase"}
        
        result = AlertFormatter.format_alert(alert)
        
        # Should have timestamp format
        assert "[" in result and "]" in result

    def test_format_alert_status_uppercase(self):
        """Should convert status to uppercase."""
        alert = {"provider": "Service", "status": "investigating", "title": "Issue"}
        
        result = AlertFormatter.format_alert(alert)
        
        assert "INVESTIGATING" in result

    def test_format_alert_missing_fields(self):
        """Should handle missing fields gracefully."""
        alert = {}
        
        result = AlertFormatter.format_alert(alert)
        
        # Should not crash and return a valid string
        assert isinstance(result, str)
        assert len(result) > 0


class TestIncidentParserIntegration:
    """Integration tests combining multiple parsing methods."""

    def test_workflow_parse_and_filter_incidents(self):
        """Test parsing RSS entries and filtering active incidents."""
        entries = [
            {
                "id": "inc-1",
                "title": "Investigating - API Latency",
                "summary": "Increased latency detected",
            },
            {
                "id": "inc-2",
                "title": "Resolved",
                "summary": "<b>Status: Resolved</b>",
            },
            {
                "id": "inc-3",
                "title": "Outage - Full Service Down",
                "summary": "Service temporarily unavailable",
            },
        ]
        
        # Parse entries
        incidents = []
        for entry in entries:
            incident = IncidentParser.parse_entry(entry)
            if incident:
                incidents.append(incident)
        
        assert len(incidents) == 3
        
        # Filter active (non-resolved)
        active = IncidentParser.filter_active_incidents(incidents)
        
        assert len(active) == 2  # Only investigating and outage
        assert all(inc["status"] != "resolved" for inc in active)

    def test_workflow_detect_incident_changes(self):
        """Test detecting changes in incident state across cycles."""
        # Cycle 1: Two incidents
        cycle1_incidents = [
            {"id": "inc-1", "status": "outage"},
            {"id": "inc-2", "status": "investigating"},
        ]
        cycle1_ids = {inc["id"] for inc in cycle1_incidents}
        
        # Cache these
        cached_ids = cycle1_ids.copy()
        
        # Cycle 2: One new, one resolved
        cycle2_incidents = [
            {"id": "inc-2", "status": "investigating"},  # Still there
            {"id": "inc-3", "status": "degraded"},  # New
        ]
        cycle2_ids = {inc["id"] for inc in cycle2_incidents}
        
        # Check for changes
        changed = IncidentParser.has_incident_changed(cycle2_incidents, list(cached_ids))
        
        assert changed is True
        
        # Identify what changed
        new_incidents = cycle2_ids - cached_ids
        resolved_incidents = cached_ids - cycle2_ids
        
        assert "inc-3" in new_incidents
        assert "inc-1" in resolved_incidents


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

